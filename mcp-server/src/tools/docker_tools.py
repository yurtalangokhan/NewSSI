"""
Docker Tools Category.
Provides tools for Docker container management.
"""

import json
import subprocess
from typing import Any, Optional

from ..core.base import BaseToolCategory


class DockerTools(BaseToolCategory):
    """Docker container management tools."""
    
    @property
    def name(self) -> str:
        return "docker"
    
    @property
    def description(self) -> str:
        return "Docker container build, run, and management"
    
    @property
    def label(self) -> str:
        return "Docker"
    
    def register_tools(self, mcp: Any) -> None:
        """Register all Docker tools with MCP."""
        
        @mcp.tool()
        def docker_build(dockerfile_path: str, image_name: str, build_args: Optional[str] = None) -> str:
            """
            Build a Docker image.
            
            Args:
                dockerfile_path: Path to Dockerfile directory
                image_name: Name for the image (e.g., myapp:latest)
                build_args: Optional build arguments as JSON (e.g., '{"ARG1": "value1"}')
            
            Returns:
                Build output
            """
            cmd = f"docker build -t {image_name}"
            
            if build_args:
                try:
                    args = json.loads(build_args)
                    for key, value in args.items():
                        cmd += f" --build-arg {key}={value}"
                except:
                    pass
            
            cmd += f" {dockerfile_path}"
            
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
                return result.stdout + result.stderr
            except Exception as e:
                return f"Docker build error: {str(e)}"
        
        @mcp.tool()
        def docker_run(image_name: str, container_name: Optional[str] = None, ports: Optional[str] = None, 
                       env_vars: Optional[str] = None, detach: bool = True) -> str:
            """
            Run a Docker container.
            
            Args:
                image_name: Image to run
                container_name: Optional container name
                ports: Port mapping as JSON (e.g., '{"8080": "80"}')
                env_vars: Environment variables as JSON (e.g., '{"KEY": "value"}')
                detach: Run in background (default: True)
            
            Returns:
                Container ID or error
            """
            cmd = "docker run"
            
            if detach:
                cmd += " -d"
            
            if container_name:
                cmd += f" --name {container_name}"
            
            if ports:
                try:
                    port_map = json.loads(ports)
                    for host_port, container_port in port_map.items():
                        cmd += f" -p {host_port}:{container_port}"
                except:
                    pass
            
            if env_vars:
                try:
                    envs = json.loads(env_vars)
                    for key, value in envs.items():
                        cmd += f" -e {key}={value}"
                except:
                    pass
            
            cmd += f" {image_name}"
            
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return result.stdout.strip() if result.stdout else result.stderr
            except Exception as e:
                return f"Docker run error: {str(e)}"
        
        @mcp.tool()
        def docker_stop(container_name: str) -> str:
            """
            Stop a Docker container.
            
            Args:
                container_name: Container name or ID
            
            Returns:
                Result message
            """
            try:
                result = subprocess.run(f"docker stop {container_name}", shell=True, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return f"Container {container_name} stopped successfully"
                return result.stderr
            except Exception as e:
                return f"Docker stop error: {str(e)}"
        
        @mcp.tool()
        def docker_logs(container_name: str, lines: int = 100) -> str:
            """
            Get Docker container logs.
            
            Args:
                container_name: Container name or ID
                lines: Number of lines to return (default: 100)
            
            Returns:
                Container logs
            """
            try:
                result = subprocess.run(f"docker logs --tail {lines} {container_name}", 
                                       shell=True, capture_output=True, text=True, timeout=30)
                return result.stdout + result.stderr
            except Exception as e:
                return f"Docker logs error: {str(e)}"
        
        @mcp.tool()
        def docker_ps(all_containers: bool = False) -> str:
            """
            List Docker containers.
            
            Args:
                all_containers: Include stopped containers
            
            Returns:
                Container list
            """
            cmd = "docker ps"
            if all_containers:
                cmd += " -a"
            cmd += " --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"
            
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return result.stdout
            except Exception as e:
                return f"Docker ps error: {str(e)}"
