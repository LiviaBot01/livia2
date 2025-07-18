#!/usr/bin/env python3
"""
Structured Schemas for Livia Chatbot
------------------------------------
Pydantic models for OpenAI Structured Outputs to ensure reliable JSON schema adherence.
Used with OpenAI Responses API for consistent, validated responses.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ===== TOOL DETECTION SCHEMAS =====

class ToolUsage(BaseModel):
    """Schema for detecting which tools are being used in a response."""
    tool_name: str = Field(description="Name of the tool being used (e.g., 'WebSearch', 'FileSearch', 'ImageGeneration')")
    confidence: float = Field(description="Confidence score 0-1 for tool detection", ge=0.0, le=1.0)
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Tool parameters if available")


class ResponseMetadata(BaseModel):
    """Metadata about the response generation process."""
    primary_tool: Optional[str] = Field(default=None, description="Primary tool used for this response")
    secondary_tools: List[str] = Field(default=[], description="Additional tools used")
    model_used: str = Field(description="OpenAI model used for generation")
    response_type: Literal["text", "structured", "tool_call", "error"] = Field(description="Type of response")
    processing_time_ms: Optional[int] = Field(default=None, description="Processing time in milliseconds")


# ===== MCP OPERATION SCHEMAS =====

class EverhourTimeEntry(BaseModel):
    """Schema for Everhour time tracking operations."""
    task_id: str = Field(description="Everhour task ID (format: ev:xxxxxxxxxx)")
    time_spent: str = Field(description="Time in format like '2h', '30m', '1.5h'")
    date: str = Field(description="Date in YYYY-MM-DD format")
    comment: Optional[str] = Field(default=None, description="Optional comment for the time entry")
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Human-readable result message")


class AsanaTaskOperation(BaseModel):
    """Schema for Asana task management operations."""
    operation_type: Literal["search", "create", "update", "complete"] = Field(description="Type of operation performed")
    workspace_id: Optional[str] = Field(default=None, description="Asana workspace ID")
    project_id: Optional[str] = Field(default=None, description="Asana project ID")
    task_id: Optional[str] = Field(default=None, description="Asana task ID")
    task_name: Optional[str] = Field(default=None, description="Task name")
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Human-readable result message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional operation details")


class GmailOperation(BaseModel):
    """Schema for Gmail operations."""
    operation_type: Literal["search", "send", "read", "archive"] = Field(description="Type of Gmail operation")
    query: Optional[str] = Field(default=None, description="Search query used")
    message_count: Optional[int] = Field(default=None, description="Number of messages found/processed")
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Human-readable result message")
    emails: Optional[List[Dict[str, Any]]] = Field(default=None, description="Email details if applicable")


# ===== SEARCH AND CONTENT SCHEMAS =====

class WebSearchResult(BaseModel):
    """Schema for web search results."""
    query: str = Field(description="Search query used")
    results_count: int = Field(description="Number of results found")
    top_results: List[Dict[str, str]] = Field(description="Top search results with title, url, snippet")
    search_summary: str = Field(description="Summary of search findings")
    sources_used: List[str] = Field(description="URLs of sources referenced in response")


class FileSearchResult(BaseModel):
    """Schema for file search results."""
    query: str = Field(description="Search query used")
    files_found: int = Field(description="Number of relevant files found")
    top_matches: List[Dict[str, Any]] = Field(description="Top file matches with metadata")
    content_summary: str = Field(description="Summary of found content")
    citations: List[str] = Field(description="File citations used in response")


# ===== IMAGE AND MEDIA SCHEMAS =====

class ImageAnalysis(BaseModel):
    """Schema for image analysis results."""
    image_url: str = Field(description="URL of the analyzed image")
    description: str = Field(description="Detailed description of the image")
    objects_detected: List[str] = Field(description="Objects/elements detected in the image")
    text_extracted: Optional[str] = Field(default=None, description="Text extracted from image if any")
    analysis_confidence: float = Field(description="Confidence in analysis accuracy", ge=0.0, le=1.0)
    suggested_actions: List[str] = Field(default=[], description="Suggested actions based on image content")


class ImageGeneration(BaseModel):
    """Schema for image generation operations."""
    prompt: str = Field(description="Prompt used for image generation")
    image_url: Optional[str] = Field(default=None, description="Generated image URL")
    generation_time_ms: Optional[int] = Field(default=None, description="Time taken to generate image")
    success: bool = Field(description="Whether generation was successful")
    message: str = Field(description="Human-readable result message")
    model_used: str = Field(default="gpt-image-1", description="Image generation model used")


class AudioTranscription(BaseModel):
    """Schema for audio transcription results."""
    file_name: str = Field(description="Original audio file name")
    file_size_mb: float = Field(description="Audio file size in MB")
    duration_seconds: Optional[float] = Field(default=None, description="Audio duration if available")
    transcription: str = Field(description="Transcribed text content")
    language_detected: Optional[str] = Field(default=None, description="Detected language")
    confidence: float = Field(description="Transcription confidence score", ge=0.0, le=1.0)
    processing_time_ms: int = Field(description="Processing time in milliseconds")


# ===== UNIFIED RESPONSE SCHEMA =====

class LiviaResponse(BaseModel):
    """Unified schema for all Livia chatbot responses."""
    response_text: str = Field(description="Main response text to display to user")
    metadata: ResponseMetadata = Field(description="Response metadata and processing info")
    
    # Tool-specific results (optional, only populated when relevant)
    everhour_result: Optional[EverhourTimeEntry] = Field(default=None)
    asana_result: Optional[AsanaTaskOperation] = Field(default=None)
    gmail_result: Optional[GmailOperation] = Field(default=None)
    web_search_result: Optional[WebSearchResult] = Field(default=None)
    file_search_result: Optional[FileSearchResult] = Field(default=None)
    image_analysis_result: Optional[ImageAnalysis] = Field(default=None)
    image_generation_result: Optional[ImageGeneration] = Field(default=None)
    audio_transcription_result: Optional[AudioTranscription] = Field(default=None)
    
    # Additional context
    error_details: Optional[Dict[str, Any]] = Field(default=None, description="Error details if any")
    suggestions: List[str] = Field(default=[], description="Suggested follow-up actions")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ===== UTILITY FUNCTIONS =====

def get_schema_for_operation(operation_type: str) -> type[BaseModel]:
    """
    Returns the appropriate Pydantic schema for a given operation type.
    
    Args:
        operation_type: Type of operation (e.g., 'everhour', 'asana', 'web_search')
    
    Returns:
        Pydantic BaseModel class for the operation
    """
    schema_mapping = {
        'everhour': EverhourTimeEntry,
        'asana': AsanaTaskOperation,
        'gmail': GmailOperation,
        'web_search': WebSearchResult,
        'file_search': FileSearchResult,
        'image_analysis': ImageAnalysis,
        'image_generation': ImageGeneration,
        'audio_transcription': AudioTranscription,
        'unified': LiviaResponse
    }
    
    return schema_mapping.get(operation_type, LiviaResponse)


def create_response_schema(include_tools: List[str] = None) -> Dict[str, Any]:
    """
    Creates a JSON schema for OpenAI Structured Outputs based on required tools.
    
    Args:
        include_tools: List of tools to include in schema (optional)
    
    Returns:
        JSON schema dictionary for OpenAI API
    """
    if include_tools is None:
        # Return full LiviaResponse schema
        return LiviaResponse.model_json_schema()
    
    # Create a minimal schema with only required tools
    # This could be expanded for more granular control
    return LiviaResponse.model_json_schema()
