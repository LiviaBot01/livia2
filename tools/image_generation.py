#!/usr/bin/env python3

import os
import base64
import tempfile
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageGenerationTool:
    
    def __init__(self):
        self.model = "gpt-image-1"
        self.supported_formats = ["png", "jpeg", "webp"]
        self.supported_sizes = ["1024x1024", "1536x1024", "1024x1536"]
        self.supported_qualities = ["standard", "hd"]
        
        logger.info("ImageGenerationTool initialized with gpt-image-1 support")
    
    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        format: str = "png",
        stream_callback=None
    ) -> Dict[str, Any]:
        from openai import OpenAI
        
        try:
            client = OpenAI()
            
            logger.info(f"Generating image with prompt: '{prompt[:100]}...'")
            logger.info(f"Settings: size={size}, quality={quality}, format={format}")

            if stream_callback:
                import asyncio

                await stream_callback("Gerando imagem...", 0)

                async def generate_image_async():
                    return client.images.generate(
                        model=self.model,
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        n=1
                    )

                generation_task = asyncio.create_task(generate_image_async())

                # Remover loop de sleep para evitar bloqueio; usar callback real se disponível
                try:
                    response = await generation_task

                    if not response.data or len(response.data) == 0:
                        raise ValueError("No image data found in response")

                    image_base64 = response.data[0].b64_json
                    revised_prompt = getattr(response.data[0], 'revised_prompt', prompt)

                    usage_info = getattr(response, 'usage', None)
                    if usage_info:
                        self._log_usage_info(usage_info, prompt)

                    await stream_callback("Imagem gerada!", 100)

                except Exception as e:
                    logger.error(f"Error during image generation: {e}")
                    await stream_callback("Erro na geração da imagem", 0)
                    raise

            else:
                response = client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=1
                )

                if not response.data or len(response.data) == 0:
                    raise ValueError("No image data found in response")

                image_base64 = response.data[0].b64_json
                revised_prompt = getattr(response.data[0], 'revised_prompt', prompt)

                usage_info = getattr(response, 'usage', None)
                if usage_info:
                    self._log_usage_info(usage_info, prompt)
            
            image_path = await self._save_temp_image(image_base64, "generated", format)
            
            image_size = os.path.getsize(image_path)
            
            result = {
                "success": True,
                "image_path": image_path,
                "image_base64": image_base64,
                "original_prompt": prompt,
                "revised_prompt": revised_prompt,
                "format": format,
                "size": size,
                "quality": quality,
                "file_size": image_size,
                "model": "gpt-image-1"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "original_prompt": prompt
            }
    

    
    async def _save_temp_image(self, image_base64: str, prefix: str, format: str) -> str:
        try:
            image_bytes = base64.b64decode(image_base64)
            
            with tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=f".{format}", 
                prefix=f"livia_{prefix}_"
            ) as temp_file:
                temp_file.write(image_bytes)
                temp_path = temp_file.name
            
            logger.debug(f"Image saved to temporary file: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error saving temporary image: {e}")
            raise
    
    def _log_usage_info(self, usage_info, prompt: str) -> None:
        try:
            input_tokens = getattr(usage_info, 'input_tokens', 0)
            output_tokens = getattr(usage_info, 'output_tokens', 0)
            total_tokens = getattr(usage_info, 'total_tokens', input_tokens + output_tokens)

            input_token_cost = 0.00001
            output_image_token_cost = 0.00004

            input_cost = (input_tokens / 1000) * input_token_cost
            output_cost = (output_tokens / 1000) * output_image_token_cost
            total_cost = input_cost + output_cost

            logger.info(f"🎨 Image generation cost: ${total_cost:.6f} (tokens: {total_tokens})")

        except Exception as e:
            logger.warning(f"Failed to log usage info: {e}")

    def cleanup_temp_file(self, file_path: str) -> None:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary file {file_path}: {e}")
    
    async def generate_image_with_progress(
        self,
        prompt: str,
        say,
        channel: str,
        thread_key: str = None,
        thread_ts: Optional[str] = None,
        size: str = "auto",
        quality: str = "auto",
        format: str = "png"
    ) -> Dict[str, Any]:
        try:
            progress_msg = None
            async def progress_callback(message: str, progress: int):
                nonlocal progress_msg
                if progress == 0:
                    progress_msg = await say(
                        text="🎨 Gerando imagem...",
                        channel=channel,
                        thread_ts=thread_ts
                    )

            result = await self.generate_image(
                prompt=prompt,
                size=size,
                quality=quality,
                format=format,
                stream_callback=progress_callback
            )

            if result.get("success"):
                image_path = result["image_path"]

                from slack_sdk import WebClient
                slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

                upload_result = slack_client.files_upload_v2(
                    channel=channel,
                    file=image_path,
                    title="Imagem gerada",
                    initial_comment="🎨 Imagem gerada",
                    thread_ts=thread_ts
                )

                os.unlink(image_path)

                return {
                    "success": True,
                    "slack_file_id": upload_result["file"]["id"],
                    "slack_file_url": upload_result["file"]["url_private"],
                    **result
                }
            else:
                await say(
                    text=f"❌ Erro na geração: {result.get('error', 'Erro desconhecido')}",
                    channel=channel,
                    thread_ts=thread_ts
                )
                return result

        except Exception as e:
            logger.error(f"Error in generate_image_with_progress: {e}")
            await say(
                text=f"❌ Erro na geração de imagem: {str(e)}",
                channel=channel,
                thread_ts=thread_ts
            )
            return {"success": False, "error": str(e)}

    def get_generation_info(self) -> Dict[str, Any]:
        return {
            "model": "gpt-image-1",
            "supported_formats": self.supported_formats,
            "supported_sizes": self.supported_sizes,
            "supported_qualities": self.supported_qualities,
            "features": [
                "Text-to-image generation",
                "High-quality output",
                "Progress updates",
                "Automatic prompt revision",
                "Multiple formats and sizes",
                "Slack integration"
            ]
        }


image_generator = ImageGenerationTool()
