"""Tool management and execution for LLM service"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import structlog
import httpx
from jsonschema import validate, ValidationError

from .config import settings
from .models import ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)

class ToolManager:
    """Manage and execute tools for LLM"""
    
    def __init__(self):
        self.tools = {}
        self.tool_schemas = {}
        self.total_executions = 0
        self.successful_executions = 0
        self.execution_times = []
        
    async def load_tools(self):
        """Load built-in tools"""
        try:
            # Built-in tools
            await self._register_builtin_tools()
            
            logger.info("Tools loaded", count=len(self.tools))
            
        except Exception as e:
            logger.error("Failed to load tools", error=str(e))
            raise
    
    async def _register_builtin_tools(self):
        """Register built-in tools"""
        
        # Web search tool
        await self.register_tool({
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            },
            "function": self._web_search
        })
        
        # Calculator tool
        await self.register_tool({
            "name": "calculator",
            "description": "Perform mathematical calculations",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            },
            "function": self._calculator
        })
        
        # Weather tool
        await self.register_tool({
            "name": "get_weather",
            "description": "Get current weather information",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Location to get weather for"
                    },
                    "units": {
                        "type": "string",
                        "description": "Temperature units (celsius/fahrenheit)",
                        "default": "celsius"
                    }
                },
                "required": ["location"]
            },
            "function": self._get_weather
        })
        
        # Time tool
        await self.register_tool({
            "name": "get_time",
            "description": "Get current time and date",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone (e.g., UTC, EST, PST)",
                        "default": "UTC"
                    },
                    "format": {
                        "type": "string",
                        "description": "Time format",
                        "default": "ISO"
                    }
                }
            },
            "function": self._get_time
        })
        
        # Email tool
        await self.register_tool({
            "name": "send_email",
            "description": "Send an email",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject"
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body"
                    }
                },
                "required": ["to", "subject", "body"]
            },
            "function": self._send_email
        })
        
        # File operations
        await self.register_tool({
            "name": "read_file",
            "description": "Read content from a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    }
                },
                "required": ["file_path"]
            },
            "function": self._read_file
        })
        
        await self.register_tool({
            "name": "write_file",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["file_path", "content"]
            },
            "function": self._write_file
        })
    
    async def register_tool(self, tool_definition: Dict[str, Any]):
        """Register a new tool"""
        try:
            name = tool_definition["name"]
            description = tool_definition["description"]
            parameters = tool_definition["parameters"]
            function = tool_definition["function"]
            
            # Validate tool definition
            if not all(key in tool_definition for key in ["name", "description", "parameters"]):
                raise ValueError("Invalid tool definition")
            
            # Store tool
            self.tools[name] = {
                "description": description,
                "parameters": parameters,
                "function": function
            }
            
            # Store schema for validation
            self.tool_schemas[name] = parameters
            
            logger.info("Tool registered", name=name)
            
        except Exception as e:
            logger.error("Tool registration failed", name=tool_definition.get("name"), error=str(e))
            raise
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a tool"""
        start_time = datetime.utcnow()
        call_id = f"{tool_name}_{int(start_time.timestamp())}"
        
        try:
            # Check if tool exists
            if tool_name not in self.tools:
                raise ValueError(f"Tool '{tool_name}' not found")
            
            tool = self.tools[tool_name]
            
            # Validate arguments
            try:
                validate(instance=arguments, schema=tool["parameters"])
            except ValidationError as e:
                raise ValueError(f"Invalid arguments: {e.message}")
            
            # Execute tool with timeout
            result = await asyncio.wait_for(
                tool["function"](arguments, context),
                timeout=settings.tool_timeout_seconds
            )
            
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Update metrics
            self.total_executions += 1
            self.successful_executions += 1
            self.execution_times.append(execution_time)
            
            if len(self.execution_times) > 1000:
                self.execution_times = self.execution_times[-1000:]
            
            logger.info("Tool executed successfully",
                       tool=tool_name,
                       execution_time_ms=execution_time)
            
            return ToolResult(
                call_id=call_id,
                result=result,
                success=True,
                execution_time_ms=execution_time
            )
            
        except asyncio.TimeoutError:
            self.total_executions += 1
            logger.error("Tool execution timeout", tool=tool_name)
            
            return ToolResult(
                call_id=call_id,
                result=None,
                success=False,
                error="Tool execution timeout",
                execution_time_ms=settings.tool_timeout_seconds * 1000
            )
            
        except Exception as e:
            self.total_executions += 1
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            logger.error("Tool execution failed", tool=tool_name, error=str(e))
            
            return ToolResult(
                call_id=call_id,
                result=None,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    async def get_available_tools(self) -> List[ToolDefinition]:
        """Get list of available tools"""
        tools = []
        
        for name, tool in self.tools.items():
            tools.append(ToolDefinition(
                name=name,
                description=tool["description"],
                parameters=tool["parameters"],
                required=tool["parameters"].get("required", [])
            ))
        
        return tools
    
    def get_success_rate(self) -> float:
        """Get tool execution success rate"""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions
    
    # Built-in tool implementations
    
    async def _web_search(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Web search tool implementation"""
        query = arguments["query"]
        num_results = arguments.get("num_results", 5)
        
        try:
            # Mock web search - in production, integrate with search API
            results = [
                {
                    "title": f"Search result {i+1} for '{query}'",
                    "url": f"https://example.com/result{i+1}",
                    "snippet": f"This is a mock search result snippet for query '{query}'. Result number {i+1}."
                }
                for i in range(num_results)
            ]
            
            return {
                "query": query,
                "results": results,
                "total_results": num_results
            }
            
        except Exception as e:
            raise Exception(f"Web search failed: {str(e)}")
    
    async def _calculator(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculator tool implementation"""
        expression = arguments["expression"]
        
        try:
            # Safe evaluation of mathematical expressions
            import ast
            import operator
            
            # Supported operations
            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
            }
            
            def eval_expr(node):
                if isinstance(node, ast.Num):
                    return node.n
                elif isinstance(node, ast.BinOp):
                    return ops[type(node.op)](eval_expr(node.left), eval_expr(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return ops[type(node.op)](eval_expr(node.operand))
                else:
                    raise TypeError(node)
            
            result = eval_expr(ast.parse(expression, mode='eval').body)
            
            return {
                "expression": expression,
                "result": result
            }
            
        except Exception as e:
            raise Exception(f"Calculation failed: {str(e)}")
    
    async def _get_weather(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Weather tool implementation"""
        location = arguments["location"]
        units = arguments.get("units", "celsius")
        
        try:
            # Mock weather data - in production, integrate with weather API
            import random
            
            temp = random.randint(15, 30) if units == "celsius" else random.randint(60, 85)
            conditions = random.choice(["sunny", "cloudy", "rainy", "partly cloudy"])
            
            return {
                "location": location,
                "temperature": temp,
                "units": units,
                "conditions": conditions,
                "humidity": random.randint(30, 80),
                "wind_speed": random.randint(5, 25)
            }
            
        except Exception as e:
            raise Exception(f"Weather lookup failed: {str(e)}")
    
    async def _get_time(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Time tool implementation"""
        timezone = arguments.get("timezone", "UTC")
        format_type = arguments.get("format", "ISO")
        
        try:
            from datetime import datetime, timezone as tz
            
            now = datetime.now(tz.utc)
            
            if format_type == "ISO":
                time_str = now.isoformat()
            else:
                time_str = now.strftime("%Y-%m-%d %H:%M:%S")
            
            return {
                "current_time": time_str,
                "timezone": timezone,
                "format": format_type,
                "timestamp": int(now.timestamp())
            }
            
        except Exception as e:
            raise Exception(f"Time lookup failed: {str(e)}")
    
    async def _send_email(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Email tool implementation"""
        to = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]
        
        try:
            # Mock email sending - in production, integrate with email service
            message_id = f"msg_{int(datetime.utcnow().timestamp())}"
            
            logger.info("Mock email sent", to=to, subject=subject)
            
            return {
                "message_id": message_id,
                "to": to,
                "subject": subject,
                "status": "sent",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            raise Exception(f"Email sending failed: {str(e)}")
    
    async def _read_file(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """File reading tool implementation"""
        file_path = arguments["file_path"]
        
        try:
            # Security check - only allow reading from safe directories
            import os
            safe_dirs = ["/tmp", "/app/data"]
            
            if not any(file_path.startswith(safe_dir) for safe_dir in safe_dirs):
                raise Exception("File access denied - unsafe path")
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return {
                    "file_path": file_path,
                    "content": content,
                    "size": len(content),
                    "exists": True
                }
            else:
                return {
                    "file_path": file_path,
                    "content": None,
                    "exists": False,
                    "error": "File not found"
                }
                
        except Exception as e:
            raise Exception(f"File reading failed: {str(e)}")
    
    async def _write_file(self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """File writing tool implementation"""
        file_path = arguments["file_path"]
        content = arguments["content"]
        
        try:
            # Security check - only allow writing to safe directories
            import os
            safe_dirs = ["/tmp", "/app/data"]
            
            if not any(file_path.startswith(safe_dir) for safe_dir in safe_dirs):
                raise Exception("File access denied - unsafe path")
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "file_path": file_path,
                "bytes_written": len(content.encode('utf-8')),
                "status": "success"
            }
            
        except Exception as e:
            raise Exception(f"File writing failed: {str(e)}")
