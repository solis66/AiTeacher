"""
缓存管理模块

提供统一的缓存服务，支持：
- 内存缓存（LRU策略）
- 作文批改结果缓存
- 缓存过期机制
- 缓存统计

设计原则：
- 自动过期：缓存项自动过期，避免内存泄漏
- LRU策略：最近最少使用的缓存项优先淘汰
- 线程安全：支持多线程访问
- 可配置：缓存大小和过期时间可配置
"""

import time
import hashlib
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from threading import Lock
from settings import get_settings

# 配置
settings = get_settings()
cache_config = settings.get_cache_config()


class LRUCache:
    """
    LRU（最近最少使用）缓存实现
    
    使用OrderedDict实现LRU策略，支持：
    - 最大容量限制
    - 自动过期
    - 线程安全
    """
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        初始化缓存
        
        参数：
            max_size: 最大缓存项数量
            ttl: 缓存过期时间（秒）
        """
        self._max_size = max_size
        self._ttl = ttl
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = Lock()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def _is_expired(self, timestamp: float) -> bool:
        """
        检查缓存项是否过期
        
        参数：
            timestamp: 缓存时间戳
            
        返回：
            bool: 是否过期
        """
        return (time.time() - timestamp) > self._ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存项
        
        参数：
            key: 缓存键
            
        返回：
            Optional[Any]: 缓存值或None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, timestamp = self._cache[key]
            
            # 检查是否过期
            if self._is_expired(timestamp):
                del self._cache[key]
                self._misses += 1
                return None
            
            # 移动到末尾表示最近使用
            self._cache.move_to_end(key)
            self._hits += 1
            
            return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存项
        
        参数：
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            # 如果已存在，删除旧的
            if key in self._cache:
                del self._cache[key]
            
            # 如果超过最大容量，删除最老的
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1
            
            # 添加新缓存项
            self._cache[key] = (value, time.time())
    
    def delete(self, key: str) -> None:
        """
        删除缓存项
        
        参数：
            key: 缓存键
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """
        清空缓存
        """
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        返回：
            Dict: 统计信息字典
        """
        with self._lock:
            return {
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions,
                'current_size': len(self._cache),
                'max_size': self._max_size
            }
    
    def __contains__(self, key: str) -> bool:
        """
        检查缓存键是否存在
        
        参数：
            key: 缓存键
            
        返回：
            bool: 是否存在
        """
        with self._lock:
            if key not in self._cache:
                return False
            
            _, timestamp = self._cache[key]
            if self._is_expired(timestamp):
                del self._cache[key]
                return False
            
            return True


class EssayReviewCache:
    """
    作文批改缓存服务
    
    提供作文批改结果的缓存功能，支持：
    - 基于作文内容的缓存键生成
    - 考虑体裁的缓存区分
    - 自动过期和清理
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        初始化缓存服务
        """
        if self._initialized:
            return
        
        config = settings.get_cache_config()
        self._cache = LRUCache(
            max_size=config.get('max_size', 1000),
            ttl=config.get('ttl', 3600)
        )
        self._enabled = config.get('enabled', True)
        
        self._initialized = True
    
    def _generate_key(self, content: str, essay_type: str) -> str:
        """
        生成缓存键
        
        参数：
            content: 作文内容
            essay_type: 作文体裁
            
        返回：
            str: 缓存键
        """
        # 使用内容摘要和体裁生成唯一键
        content_hash = hashlib.md5(content.encode()).hexdigest()
        type_hash = hashlib.md5(essay_type.encode()).hexdigest()
        
        return f"{content_hash}_{type_hash}"
    
    def get(self, content: str, essay_type: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的批改结果
        
        参数：
            content: 作文内容
            essay_type: 作文体裁
            
        返回：
            Optional[Dict]: 批改结果或None
        """
        if not self._enabled:
            return None
        
        key = self._generate_key(content, essay_type)
        return self._cache.get(key)
    
    def set(self, content: str, essay_type: str, result: Dict[str, Any]) -> None:
        """
        设置缓存的批改结果
        
        参数：
            content: 作文内容
            essay_type: 作文体裁
            result: 批改结果
        """
        if not self._enabled:
            return
        
        key = self._generate_key(content, essay_type)
        self._cache.set(key, result)
    
    def invalidate(self, content: str, essay_type: str) -> None:
        """
        使缓存失效
        
        参数：
            content: 作文内容
            essay_type: 作文体裁
        """
        if not self._enabled:
            return
        
        key = self._generate_key(content, essay_type)
        self._cache.delete(key)
    
    def clear(self) -> None:
        """
        清空所有缓存
        """
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        返回：
            Dict: 统计信息字典
        """
        return self._cache.get_stats()
    
    @property
    def enabled(self) -> bool:
        """
        缓存是否启用
        
        返回：
            bool: 是否启用
        """
        return self._enabled


# 创建全局缓存实例
essay_cache = EssayReviewCache()


def get_cache() -> EssayReviewCache:
    """
    获取缓存实例（便捷函数）
    
    返回：
        EssayReviewCache: 缓存实例
    """
    return essay_cache


def cache_decorator(func):
    """
    缓存装饰器
    
    用于装饰作文批改函数，自动处理缓存逻辑
    
    参数：
        func: 被装饰的函数
        
    返回：
        callable: 装饰后的函数
    """
    def wrapper(content: str, essay_type: str = '', *args, **kwargs):
        # 如果缓存未启用，直接调用原函数
        if not essay_cache.enabled:
            return func(content, essay_type, *args, **kwargs)
        
        # 尝试从缓存获取
        cached_result = essay_cache.get(content, essay_type)
        if cached_result is not None:
            return cached_result
        
        # 调用原函数
        result = func(content, essay_type, *args, **kwargs)
        
        # 缓存结果
        essay_cache.set(content, essay_type, result)
        
        return result
    
    return wrapper
