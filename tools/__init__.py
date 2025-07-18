#!/usr/bin/env python3

from .web_search import WebSearchTool
from .image_generation import ImageGenerationTool, image_generator

class ImageProcessor:

    @staticmethod
    def extract_image_urls(event):
        import re
        import os
        import logging

        logger = logging.getLogger(__name__)
        image_urls = []

        files = event.get("files", [])
        for file in files:
            if file.get("mimetype", "").startswith("image/"):
                if "url_private" in file:
                    slack_image_url = f"{file['url_private']}?token={os.environ.get('SLACK_BOT_TOKEN', '')}"
                    image_urls.append(slack_image_url)
                    logger.info(f"Found uploaded image: {file.get('name', 'unknown')} - {file['url_private']}")

        text = event.get("text", "")

        url_patterns = [
            r'https?://[^\s<>]+\.(?:jpg|jpeg|png|gif|webp|bmp|tiff)(?:\?[^\s<>]*)?',
            r'https?://[^\s<>]*(?:imgur|flickr|instagram|twitter|facebook|ichef\.bbci)[^\s<>]*',
            r'https?://[^\s<>]*\.(?:com|org|net|co\.uk)/[^\s<>]*\.(?:jpg|jpeg|png|gif|webp)',
            r'https?://ichef\.bbci\.co\.uk/[^\s<>]*',
        ]

        for pattern in url_patterns:
            found_urls = re.findall(pattern, text, re.IGNORECASE)
            for url in found_urls:
                url = re.sub(r'[.,;!?]+$', '', url)
                if url not in image_urls:
                    image_urls.append(url)
                    logger.info(f"Found image URL in text: {url}")

        if image_urls:
            logger.info(f"Total images found: {len(image_urls)}")

        return image_urls

    @staticmethod
    async def process_image_urls(image_urls):
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"🖼️ IMAGE PROCESSOR - Processing {len(image_urls)} images")
        
        processed_urls = []
        for i, img_url in enumerate(image_urls):
            logger.info(f"   Processing image {i+1}/{len(image_urls)}: {img_url[:80]}{'...' if len(img_url) > 80 else ''}")
            processed_url = await ImageProcessor.process_slack_image(img_url)
            if processed_url:
                processed_urls.append(processed_url)
                logger.info(f"   ✅ Image {i+1} processed successfully")
            else:
                logger.warning(f"   ❌ Failed to process image {i+1}")

        logger.info(f"🖼️ IMAGE PROCESSING COMPLETE - {len(processed_urls)}/{len(image_urls)} successful")
        return processed_urls

    @staticmethod
    async def process_slack_image(image_url):
        import logging
        import os

        logger = logging.getLogger(__name__)

        try:
            if "files.slack.com" in image_url:
                logger.info(f"      📥 Downloading Slack image...")
                import aiohttp
                import base64

                headers = {
                    "Authorization": f"Bearer {os.environ.get('SLACK_BOT_TOKEN', '')}"
                }

                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url, headers=headers) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            content_type = response.headers.get('content-type', 'image/jpeg')
                            base64_image = base64.b64encode(image_data).decode('utf-8')
                            data_url = f"data:{content_type};base64,{base64_image}"
                            logger.info(f"      ✅ Slack image converted to base64 ({len(image_data)} bytes, {content_type})")
                            return data_url
                        else:
                            logger.error(f"      ❌ Failed to download Slack image: HTTP {response.status}")
                            return None
            else:
                logger.info(f"      🌐 Using external URL as-is")
                return image_url

        except Exception as e:
            logger.error(f"      ❌ Error processing image URL {image_url}: {e}")
            return None

__all__ = [
    "WebSearchTool",
    "ImageProcessor",
    "ImageGenerationTool",
    "image_generator"
]
