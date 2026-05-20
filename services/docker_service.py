"""
Docker management service using Docker SDK for Python.
"""

import logging
from typing import List, Dict, Any, Optional

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Docker SDK not available. Install with: pip install docker")

logger = logging.getLogger(__name__)


def get_docker_client():
    """Get Docker client instance."""
    if not DOCKER_AVAILABLE:
        raise ImportError("Docker SDK not installed")
    
    try:
        client = docker.from_env()
        return client
    except DockerException as e:
        logger.error(f"Failed to connect to Docker: {e}")
        raise


def list_containers(all_containers: bool = False) -> List[Dict[str, Any]]:
    """
    List all Docker containers.
    
    Args:
        all_containers: If True, include stopped containers
    
    Returns:
        List of container information dictionaries
    """
    if not DOCKER_AVAILABLE:
        return []
    
    try:
        client = get_docker_client()
        containers = client.containers.list(all=all_containers)
        
        container_list = []
        for container in containers:
            try:
                stats = container.stats(stream=False) if container.status == 'running' else None
                
                info = {
                    'id': container.short_id,
                    'name': container.name,
                    'image': container.image.tags[0] if container.image.tags else 'unknown',
                    'status': container.status,
                    'state': container.attrs['State']
                }
                
                # Calculate CPU and memory usage if running
                if stats:
                    cpu_percent = calculate_cpu_percent(stats)
                    memory_usage = stats['memory_stats'].get('usage', 0)
                    
                    info['cpu'] = cpu_percent
                    info['memory'] = memory_usage
                
                container_list.append(info)
            
            except Exception as e:
                logger.warning(f"Failed to get stats for container {container.name}: {e}")
                container_list.append({
                    'id': container.short_id,
                    'name': container.name,
                    'status': container.status
                })
        
        return container_list
    
    except DockerException as e:
        logger.error(f"Failed to list containers: {e}")
        return []


def calculate_cpu_percent(stats: Dict) -> float:
    """Calculate CPU percentage from Docker stats."""
    try:
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                   stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                      stats['precpu_stats']['system_cpu_usage']
        
        if system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * 100.0
            return round(cpu_percent, 2)
    except (KeyError, ZeroDivisionError):
        pass
    
    return 0.0


def get_container(name_or_id: str):
    """Get a container by name or ID."""
    if not DOCKER_AVAILABLE:
        raise ImportError("Docker SDK not installed")
    
    try:
        client = get_docker_client()
        return client.containers.get(name_or_id)
    except NotFound:
        raise ValueError(f"Container '{name_or_id}' not found")
    except DockerException as e:
        logger.error(f"Failed to get container {name_or_id}: {e}")
        raise


def restart_container(name_or_id: str) -> bool:
    """
    Restart a Docker container.
    
    Args:
        name_or_id: Container name or ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        container = get_container(name_or_id)
        container.restart(timeout=10)
        logger.info(f"Restarted container {name_or_id}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to restart container {name_or_id}: {e}")
        raise


def stop_container(name_or_id: str) -> bool:
    """
    Stop a Docker container.
    
    Args:
        name_or_id: Container name or ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        container = get_container(name_or_id)
        container.stop(timeout=10)
        logger.info(f"Stopped container {name_or_id}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to stop container {name_or_id}: {e}")
        raise


def start_container(name_or_id: str) -> bool:
    """
    Start a Docker container.
    
    Args:
        name_or_id: Container name or ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        container = get_container(name_or_id)
        container.start()
        logger.info(f"Started container {name_or_id}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to start container {name_or_id}: {e}")
        raise


def get_container_logs(name_or_id: str, lines: int = 50) -> str:
    """
    Get logs from a Docker container.
    
    Args:
        name_or_id: Container name or ID
        lines: Number of lines to retrieve
    
    Returns:
        Container logs as string
    """
    try:
        from services.readonly.constants import MAX_DOCKER_HOST_LOG_LINES

        lines = max(1, min(int(lines), MAX_DOCKER_HOST_LOG_LINES))
        container = get_container(name_or_id)
        logs = container.logs(tail=lines, timestamps=True).decode('utf-8', errors='replace')
        return logs
    
    except Exception as e:
        logger.error(f"Failed to get logs for container {name_or_id}: {e}")
        raise


def detect_unhealthy_containers() -> List[Dict[str, Any]]:
    """
    Detect unhealthy or crashed containers.
    
    Returns:
        List of unhealthy container information
    """
    try:
        all_containers = list_containers(all_containers=True)
        
        unhealthy = []
        for container in all_containers:
            status = container.get('status', '').lower()
            state = container.get('state', {})
            
            # Check for unhealthy states
            if status in ['exited', 'dead', 'restarting']:
                unhealthy.append(container)
            elif state.get('Health', {}).get('Status') == 'unhealthy':
                unhealthy.append(container)
        
        return unhealthy
    
    except Exception as e:
        logger.error(f"Failed to detect unhealthy containers: {e}")
        return []


def get_container_stats_summary(name_or_id: str) -> Dict[str, Any]:
    """Get detailed stats for a specific container."""
    try:
        container = get_container(name_or_id)
        
        if container.status != 'running':
            return {'status': container.status, 'running': False}
        
        stats = container.stats(stream=False)
        
        cpu_percent = calculate_cpu_percent(stats)
        memory_usage = stats['memory_stats'].get('usage', 0)
        memory_limit = stats['memory_stats'].get('limit', 0)
        memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
        
        # Network stats
        networks = stats.get('networks', {})
        total_rx = sum(net.get('rx_bytes', 0) for net in networks.values())
        total_tx = sum(net.get('tx_bytes', 0) for net in networks.values())
        
        return {
            'status': container.status,
            'running': True,
            'cpu_percent': cpu_percent,
            'memory_usage': memory_usage,
            'memory_limit': memory_limit,
            'memory_percent': memory_percent,
            'network_rx': total_rx,
            'network_tx': total_tx
        }
    
    except Exception as e:
        logger.error(f"Failed to get container stats: {e}")
        return {'error': str(e)}
