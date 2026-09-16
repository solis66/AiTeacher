"""
作文批改工作台路由

提供“提交批改 → 查询状态/详情 → 保存人工修改 → 导出 → 重试/删除”的完整接口。

接口清单：
    POST   /api/review                      创建批改任务（multipart，支持多图/多页PDF；可带 student）
    GET    /api/review/list                 当前用户的批改记录列表
    GET    /api/review/students             当前账号名下出现过的学生名（供老师选择）
    GET    /api/review/<rid>                批改记录详情（含分页文字与行坐标）
    GET    /api/review/<rid>/page/<name>    获取页面图片
    POST   /api/review/<rid>/save           保存人工修改（评分/评语/点评/润色/手工批注）
    POST   /api/review/<rid>/retry          失败后重试
    GET    /api/review/<rid>/export         导出 PDF
    DELETE /api/review/<rid>                删除记录

数据隔离：所有接口都以 X-Username 作为归属键，只能访问自己的记录，
         因此“分享/导出”不会暴露其他作文记录。
学生归属：owner = 提交者（隔离键）；student = 作文所属学生（学情检索键）。
         学生自己提交时 student 缺省为 owner，老师代提交时显式填写。
"""

import logging
from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from services.review_workbench import ReviewWorkbench

logger = logging.getLogger(__name__)

review_bp = Blueprint('review', __name__)

# 工作台实例（数据根目录：data/reviews）
_ROOT = Path(__file__).resolve().parents[1] / 'data' / 'reviews'
workbench = ReviewWorkbench(_ROOT)


def current_owner():
    """获取当前用户标识。沿用项目既有约定：X-Username 请求头。"""
    return request.headers.get('X-Username') or 'anonymous'


def page_owner():
    """
    页面图片专用归属解析。

    浏览器对 <img src> 的请求无法自定义请求头，如果只认 X-Username，
    标签会退化成 anonymous，导致图片一律 404（批改页主图、页面缩略图、
    首页入口卡缩略图全部空白）。因此这里额外接受 ?owner= 查询参数。

    安全性说明：X-Username 本身由前端自由填写，只用于“诚实用户之间的数据隔离”，
    不是身份认证手段；查询参数与请求头的信任级别相同，不引入新的越权面。
    """
    return (request.headers.get('X-Username')
            or request.args.get('owner')
            or 'anonymous')


def summarize(record, detail=False):
    """
    裁剪返回给前端的记录结构。

    detail=False 时剔除 pages.lines 等大字段，供列表与轮询使用，避免响应体过大。
    """
    pages = record.get('pages') or []
    thumb = pages[0]['file'] if pages else None
    data = {
        'id': record['id'],
        'version': record['version'],
        'status': record['status'],
        'error': record.get('error'),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at'),
        'input': record.get('input'),
        'student': workbench.student_of(record),
        'attachment_count': len(record.get('attachments') or []),
        'page_count': len(pages),
        'thumb': thumb,
        'pages_ready': record.get('pages_ready', False),
        'score': (record.get('result') or {}).get('score'),
        'rating': (record.get('result') or {}).get('rating'),
    }
    if detail:
        data['pages'] = pages
        data['attachments'] = record.get('attachments') or []
        data['result'] = record.get('result')
        data['marks'] = record.get('marks') or []
    return data


@review_bp.route('/api/review', methods=['POST'])
def create_review():
    """创建批改任务：接收年级、题目、题干要求、正文与附件（体裁可选，留空由 AI 依题干判定）。"""
    try:
        owner = current_owner()
        grade = (request.form.get('grade') or '').strip()
        essay_type = (request.form.get('essay_type') or '').strip()
        title = request.form.get('title') or ''
        requirements = request.form.get('requirements') or ''
        body = request.form.get('body') or ''
        # 学生归属：老师代学生提交时填写；学生自己提交时留空，由后端取 owner
        student = request.form.get('student') or ''

        # 按前端排列顺序收集附件（同名多文件时顺序即为用户排序结果）
        uploads = []
        for storage in request.files.getlist('files'):
            if storage and storage.filename:
                uploads.append((storage.filename, storage.read()))

        record = workbench.create(owner, grade, essay_type, title, requirements, body, uploads, student)
        return jsonify({'success': True, 'data': summarize(record)})
    except ValueError as exc:
        # 校验类错误（含“请重新输入jpg格式的图片”）原样返回给用户
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        logger.error('创建批改任务失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': f'创建批改任务失败：{exc}'}), 500


@review_bp.route('/api/review/students', methods=['GET'])
def list_students():
    """
    列出当前账号名下出现过的学生名（供老师选择/前端提示）。

    名单直接从既有批改记录推导，不额外维护学生表。
    """
    try:
        return jsonify({'success': True, 'data': workbench.students(current_owner())})
    except Exception as exc:
        logger.error('查询学生名单失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': '查询学生名单失败'}), 500


@review_bp.route('/api/review/list', methods=['GET'])
def list_reviews():
    """列出当前用户的批改记录（按时间倒序）。"""
    try:
        items = [summarize(r) for r in workbench.list(current_owner())]
        return jsonify({'success': True, 'data': items})
    except Exception as exc:
        logger.error('查询批改列表失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': '查询批改列表失败'}), 500


@review_bp.route('/api/review/<rid>', methods=['GET'])
def get_review(rid):
    """获取单条批改记录详情。"""
    record = workbench.get(rid, current_owner())
    if record is None:
        return jsonify({'success': False, 'message': '批改记录不存在'}), 404
    return jsonify({'success': True, 'data': summarize(record, detail=True)})


@review_bp.route('/api/review/<rid>/page/<path:name>', methods=['GET'])
def get_page(rid, name):
    """获取页面图片（原始作文/渲染页）。"""
    try:
        path = workbench.page_file(rid, page_owner(), name)
    except ValueError:
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    response = send_file(path)
    # 图片不会再变（重试会覆盖同名文件，因此按记录版本做弱缓存）
    response.headers['Cache-Control'] = 'private, max-age=300'
    return response


@review_bp.route('/api/review/<rid>/save', methods=['POST'])
def save_review(rid):
    """
    保存人工修改。

    请求体：{ version, score?, rating?, overall_comment?, dimensions?, rewrites?,
             corrections?, analysis?, highlights?, suggestions?,
             polished_title?, polished_text?, marks? }
    """
    payload = request.get_json(silent=True) or {}
    try:
        record = workbench.save(rid, current_owner(), payload.get('version'), payload)
        return jsonify({'success': True, 'data': summarize(record)})
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        logger.error('保存批改记录失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': '保存失败，请稍后重试'}), 500


@review_bp.route('/api/review/<rid>/retry', methods=['POST'])
def retry_review(rid):
    """失败后重试批改。"""
    try:
        workbench.retry(rid, current_owner())
        record = workbench.get(rid, current_owner())
        return jsonify({'success': True, 'data': summarize(record)})
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        logger.error('重试批改失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': '重试失败，请稍后重试'}), 500


@review_bp.route('/api/review/<rid>/export', methods=['GET'])
def export_review(rid):
    """导出已保存版本为 PDF。"""
    fmt = (request.args.get('format') or 'pdf').lower()
    if fmt != 'pdf':
        return jsonify({'success': False, 'message': '不支持的导出格式'}), 400
    try:
        content, mimetype = workbench.export(rid, current_owner(), fmt)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:
        logger.error('导出失败: %s', exc, exc_info=True)
        return jsonify({'success': False, 'message': f'导出失败：{exc}'}), 500

    return send_file(BytesIO(content), mimetype=mimetype, as_attachment=True,
                     download_name=f'ai批改结果.{fmt}')


@review_bp.route('/api/review/<rid>', methods=['DELETE'])
def delete_review(rid):
    """删除批改记录及其文件。"""
    ok = workbench.delete(rid, current_owner())
    return jsonify({'success': ok, 'message': '删除成功' if ok else '记录不存在'})
