#!/usr/bin/env python3
"""
Recommendations Module
Provides "More like this" suggestions and discovery feeds
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Dict, Optional


class Recommendations:
    """Generate video recommendations"""
    
    def __init__(self, search_func):
        """
        Args:
            search_func: async function that takes a query and returns list of video dicts
        """
        self.search_func = search_func
    
    async def more_like_this(self, video: dict, limit: int = 8) -> list:
        """
        Get 'More like this' recommendations for a video.
        Searches the same channel and uses the video title as a query.
        """
        results = []
        channel = video.get('channel', '')
        title = video.get('title', '')
        
        # If we have a channel, search for that channel's videos
        if channel and channel != 'Unknown':
            channel_videos = await self._search_channel(channel, limit // 2)
            results.extend(channel_videos)
        
        # Search using video title (only if it's meaningful)
        if title and title != 'Unknown' and len(title) > 5:
            title_videos = await self._search_title(title, limit - len(results))
            # Filter out videos we already have
            seen_ids = {v['id'] for v in results}
            for v in title_videos:
                if v['id'] not in seen_ids:
                    results.append(v)
                    if len(results) >= limit:
                        break
        
        # If we have nothing, fall back to a broad search
        if not results:
            results = await self._search_broad(limit)
        
        return results[:limit]
    
    async def _search_channel(self, channel: str, limit: int) -> list:
        """Search for videos from a specific channel"""
        query = f"site:{channel}" if channel else "popular"
        return await self.search_func(query, limit)
    
    async def _search_title(self, title: str, limit: int) -> list:
        """Search using video title as query"""
        return await self.search_func(title, limit)
    
    async def _search_broad(self, limit: int) -> list:
        """Get a broad discovery feed"""
        # Search for popular categories
        queries = ["music", "gaming", "news", "tech", "education"]
        results = []
        for q in queries:
            if len(results) >= limit:
                break
            try:
                videos = await self.search_func(q, limit - len(results))
                results.extend(videos)
            except:
                continue
        return results[:limit]


# Sync wrapper for non-async contexts
class SyncRecommendations:
    """Sync wrapper around Recommendations for use in synchronous code"""
    
    def __init__(self, search_func):
        self.async_recommendations = Recommendations(search_func)
    
    def more_like_this(self, video: dict, limit: int = 8) -> list:
        import asyncio
        return asyncio.run(self.async_recommendations.more_like_this(video, limit))
    
    def discovery_feed(self, limit: int = 12) -> list:
        import asyncio
        return asyncio.run(self.async_recommendations._search_broad(limit))