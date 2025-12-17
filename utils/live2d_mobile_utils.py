# -*- coding: utf-8 -*-
"""
Live2D移动端工具集

整合Live2D纹理压缩和移动端静态文件处理功能。
"""

import os
import re
import json
import logging
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from PIL import Image
import io

logger = logging.getLogger("Main")


class Live2DTextureCompressor:
    """Live2D纹理压缩器"""
    
    def __init__(self, compression_quality=85):
        """
        初始化压缩器
        
        Args:
            compression_quality: PNG压缩质量 (1-100, 数值越小压缩率越高)
        """
        self.compression_quality = max(1, min(100, compression_quality))
        self.compressed_cache = {}  # 缓存已压缩的纹理
    
    def compress_texture(self, texture_path: str) -> bytes:
        """
        压缩单个PNG纹理文件
        
        Args:
            texture_path: 纹理文件路径
            
        Returns:
            压缩后的PNG数据 (bytes)
        """
        try:
            # 检查缓存
            if texture_path in self.compressed_cache:
                return self.compressed_cache[texture_path]
            
            # 检查文件是否存在
            if not os.path.exists(texture_path):
                logger.warning(f"纹理文件不存在: {texture_path}")
                return None
            
            # 打开并压缩图像
            with Image.open(texture_path) as img:
                # 确保图像是RGBA模式（PNG通常需要透明度）
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # 使用最高压缩比优化PNG
                optimized_img = io.BytesIO()
                img.save(optimized_img, 
                        format='PNG',
                        optimize=True,  # 启用优化
                        compress_level=9,  # 最高压缩级别
                        quality=self.compression_quality)
                
                compressed_data = optimized_img.getvalue()
                
                # 缓存结果
                self.compressed_cache[texture_path] = compressed_data
                
                original_size = os.path.getsize(texture_path)
                compressed_size = len(compressed_data)
                compression_ratio = (1 - compressed_size / original_size) * 100
                
                logger.info(f"纹理压缩完成: {texture_path} "
                          f"({original_size} -> {compressed_size} bytes, "
                          f"压缩率: {compression_ratio:.1f}%)")
                
                return compressed_data
                
        except Exception as e:
            logger.error(f"压缩纹理失败 {texture_path}: {e}")
            return None
    
    def get_model_textures(self, model_config_path: str) -> list:
        """
        从Live2D模型配置文件中提取所有纹理文件路径
        
        Args:
            model_config_path: .model3.json文件路径
            
        Returns:
            纹理文件路径列表
        """
        try:
            if not os.path.exists(model_config_path):
                logger.error(f"模型配置文件不存在: {model_config_path}")
                return []
            
            with open(model_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            textures = []
            model_dir = os.path.dirname(model_config_path)
            
            # 提取纹理文件路径
            if 'FileReferences' in config and 'Textures' in config['FileReferences']:
                for texture_ref in config['FileReferences']['Textures']:
                    texture_path = os.path.join(model_dir, texture_ref)
                    textures.append(texture_path)
            
            return textures
            
        except Exception as e:
            logger.error(f"提取模型纹理失败 {model_config_path}: {e}")
            return []
    
    def compress_model_textures(self, model_config_path: str) -> dict:
        """
        压缩Live2D模型的所有纹理
        
        Args:
            model_config_path: .model3.json文件路径
            
        Returns:
            压缩结果字典: {纹理路径: 压缩数据}
        """
        textures = self.get_model_textures(model_config_path)
        compressed_textures = {}
        
        for texture_path in textures:
            compressed_data = self.compress_texture(texture_path)
            if compressed_data:
                compressed_textures[texture_path] = compressed_data
        
        return compressed_textures
    
    def clear_cache(self):
        """清空压缩缓存"""
        self.compressed_cache.clear()


# 全局压缩器实例
_global_compressor = None


def get_compressor() -> Live2DTextureCompressor:
    """获取全局压缩器实例"""
    global _global_compressor
    if _global_compressor is None:
        _global_compressor = Live2DTextureCompressor()
    return _global_compressor


def compress_live2d_texture(texture_path: str) -> bytes:
    """
    压缩单个Live2D纹理文件（便捷函数）
    
    Args:
        texture_path: 纹理文件路径
        
    Returns:
        压缩后的PNG数据
    """
    compressor = get_compressor()
    return compressor.compress_texture(texture_path)


def get_model_texture_paths(model_config_path: str) -> list:
    """
    获取模型的所有纹理文件路径（便捷函数）
    
    Args:
        model_config_path: .model3.json文件路径
        
    Returns:
        纹理文件路径列表
    """
    compressor = get_compressor()
    return compressor.get_model_textures(model_config_path)


def compress_all_model_textures(model_config_path: str) -> dict:
    """
    压缩模型的所有纹理（便捷函数）
    
    Args:
        model_config_path: .model3.json文件路径
        
    Returns:
        压缩结果字典
    """
    compressor = get_compressor()
    return compressor.compress_model_textures(model_config_path)


class MobileStaticFiles(StaticFiles):
    """移动端静态文件处理器，自动压缩Live2D纹理"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.live2d_texture_pattern = re.compile(r'.*\\.(png|PNG)$')
        self.live2d_model_pattern = re.compile(r'.*\\.model3\\.json$')
    
    def is_live2d_texture(self, path: str) -> bool:
        """检查路径是否为Live2D纹理文件"""
        # 检查文件扩展名
        if not self.live2d_texture_pattern.match(path):
            return False
        
        # 检查路径是否包含live2d相关目录
        live2d_keywords = ['live2d', 'model', 'texture', 'mao_pro']
        path_lower = path.lower()
        
        for keyword in live2d_keywords:
            if keyword in path_lower:
                return True
        
        return False
    
    async def get_response(self, path: str, scope):
        """
        重写get_response方法，对Live2D纹理进行压缩
        """
        # 先获取原始响应
        response = await super().get_response(path, scope)
        
        # 如果是404，直接返回
        if response.status_code == 404:
            return response
        
        # 检查是否为Live2D纹理文件
        if self.is_live2d_texture(path):
            try:
                # 获取文件完整路径
                full_path = Path(self.directory) / path
                
                # 压缩纹理
                compressed_data = compress_live2d_texture(str(full_path))
                
                if compressed_data:
                    # 创建新的响应，使用压缩后的数据
                    headers = dict(response.headers)
                    headers['Content-Type'] = 'image/png'
                    headers['Content-Length'] = str(len(compressed_data))
                    
                    # 添加压缩标记头
                    headers['X-Texture-Compressed'] = 'true'
                    
                    return Response(
                        content=compressed_data,
                        status_code=200,
                        headers=headers,
                        media_type='image/png'
                    )
                else:
                    logger.warning(f"纹理压缩失败，使用原始文件: {path}")
                    
            except Exception as e:
                logger.error(f"处理Live2D纹理时出错 {path}: {e}")
                # 出错时返回原始文件
        
        # 对于JavaScript文件，确保正确的Content-Type
        if path.endswith('.js'):
            response.headers['Content-Type'] = 'application/javascript'
        
        return response