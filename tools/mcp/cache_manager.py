#!/usr/bin/env python3

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class MCPCacheManager:
    
    def __init__(self, default_ttl: int = 600):
        self.default_ttl = default_ttl
        self.cache_stats: Dict[str, Dict[str, Any]] = {}
        self.last_refresh: Dict[str, float] = {}
        
    def register_server(self, server: Any, name: str, ttl: Optional[int] = None) -> None:
        cache_ttl = ttl or self.default_ttl
        self.cache_stats[name] = {
            "server": server,
            "ttl": cache_ttl,
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
            "last_refresh": 0
        }
        self.last_refresh[name] = time.time()
        logger.info(f"📋 Registered MCP server '{name}' with {cache_ttl}s TTL cache")
    
    async def check_and_refresh_cache(self, server_name: str) -> bool:
        if server_name not in self.cache_stats:
            logger.warning(f"Server '{server_name}' not registered in cache manager")
            return False
            
        stats = self.cache_stats[server_name]
        current_time = time.time()
        time_since_refresh = current_time - self.last_refresh[server_name]
        
        if time_since_refresh > stats["ttl"]:
            logger.info(f"🔄 Cache TTL expired for '{server_name}' ({time_since_refresh:.1f}s > {stats['ttl']}s)")
            await self.invalidate_cache(server_name)
            return True
            
        return False
    
    async def invalidate_cache(self, server_name: str) -> None:
        if server_name not in self.cache_stats:
            logger.warning(f"Server '{server_name}' not registered in cache manager")
            return
            
        stats = self.cache_stats[server_name]
        server = stats["server"]
        
        try:
            await server.invalidate_tools_cache()
            stats["invalidations"] += 1
            self.last_refresh[server_name] = time.time()
            logger.info(f"✅ Cache invalidated for '{server_name}'")
        except Exception as e:
            logger.error(f"❌ Failed to invalidate cache for '{server_name}': {e}")
    
    async def invalidate_all_caches(self) -> None:
        logger.info("🔄 Invalidating all MCP caches...")
        
        tasks = []
        for server_name in self.cache_stats.keys():
            tasks.append(self.invalidate_cache(server_name))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"✅ Invalidated {len(tasks)} MCP caches")
    
    def record_cache_hit(self, server_name: str) -> None:
        if server_name in self.cache_stats:
            self.cache_stats[server_name]["hits"] += 1
    
    def record_cache_miss(self, server_name: str) -> None:
        if server_name in self.cache_stats:
            self.cache_stats[server_name]["misses"] += 1
    
    def get_cache_stats(self) -> Dict[str, Dict[str, Any]]:
        stats_summary = {}
        
        for name, stats in self.cache_stats.items():
            total_requests = stats["hits"] + stats["misses"]
            hit_rate = (stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            
            stats_summary[name] = {
                "hits": stats["hits"],
                "misses": stats["misses"],
                "hit_rate": f"{hit_rate:.1f}%",
                "invalidations": stats["invalidations"],
                "ttl": stats["ttl"],
                "last_refresh": stats["last_refresh"]
            }
        
        return stats_summary
    
    def log_cache_stats(self) -> None:
        stats = self.get_cache_stats()
        
        if not stats:
            logger.info("📊 No MCP cache statistics available")
            return
        
        logger.info("📊 MCP Cache Statistics:")
        for name, server_stats in stats.items():
            logger.info(f"   {name}: {server_stats['hit_rate']} hit rate, "
                       f"{server_stats['invalidations']} invalidations, "
                       f"{server_stats['ttl']}s TTL")


class CachedMCPWrapper:
    
    def __init__(self, server: Any, ttl: int = 600, name: Optional[str] = None):
        self.server = server
        self.ttl = ttl
        self.name = name or f"MCP-{id(server)}"
        self._last_refresh = 0
    
    async def __aenter__(self):
        result = await self.server.__aenter__()
        self._last_refresh = time.time()
        logger.info(f"🚀 Started cached MCP '{self.name}' with {self.ttl}s TTL")
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        return await self.server.__aexit__(exc_type, exc, tb)
    
    async def list_tools(self):
        current_time = time.time()
        

        if current_time - self._last_refresh > self.ttl:
            logger.info(f"🔄 TTL expired for '{self.name}', invalidating cache")
            await self.server.invalidate_tools_cache()
            self._last_refresh = current_time
        
        return await self.server.list_tools()
    
    def __getattr__(self, name):
        return getattr(self.server, name)



cache_manager = MCPCacheManager()



async def setup_mcp_caching(servers: List[tuple], default_ttl: int = 600) -> None:
    logger.info(f"🚀 Setting up MCP caching for {len(servers)} servers...")
    
    for server_info in servers:
        if len(server_info) == 2:
            server, name = server_info
            ttl = default_ttl
        elif len(server_info) == 3:
            server, name, ttl = server_info
        else:
            logger.error(f"Invalid server info: {server_info}")
            continue
        
        cache_manager.register_server(server, name, ttl)
    
    logger.info("✅ MCP caching setup complete")


async def refresh_all_mcp_caches() -> None:
    await cache_manager.invalidate_all_caches()


def log_mcp_cache_performance() -> None:
    cache_manager.log_cache_stats()
