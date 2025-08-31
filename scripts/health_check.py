#!/usr/bin/env python3
"""
Comprehensive health check script for Voice Assistant Platform
"""

import asyncio
import aiohttp
import sys
import json
from datetime import datetime
from typing import Dict, List, Tuple

# Service endpoints
SERVICES = {
    "gateway": "http://localhost:8080/health",
    "auth": "http://localhost:8001/health", 
    "speech": "http://localhost:8002/health",
    "intent": "http://localhost:8003/health",
    "orchestrator": "http://localhost:8004/health",
    "rag": "http://localhost:8005/health",
    "tts": "http://localhost:8006/health",
    "llm": "http://localhost:8007/health",
    "analytics": "http://localhost:8008/health"
}

async def check_service(session: aiohttp.ClientSession, name: str, url: str) -> Tuple[str, bool, Dict]:
    """Check health of a single service"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                return name, True, data
            else:
                return name, False, {"error": f"HTTP {response.status}"}
    except Exception as e:
        return name, False, {"error": str(e)}

async def run_health_checks() -> Dict[str, Tuple[bool, Dict]]:
    """Run health checks for all services"""
    results = {}
    
    async with aiohttp.ClientSession() as session:
        tasks = [check_service(session, name, url) for name, url in SERVICES.items()]
        responses = await asyncio.gather(*tasks)
        
        for name, healthy, data in responses:
            results[name] = (healthy, data)
    
    return results

def print_results(results: Dict[str, Tuple[bool, Dict]]):
    """Print health check results"""
    print(f"\n🏥 Voice Assistant Platform Health Check")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    healthy_count = 0
    total_count = len(results)
    
    for service, (healthy, data) in results.items():
        status = "✅ HEALTHY" if healthy else "❌ UNHEALTHY"
        print(f"{service.upper():12} | {status}")
        
        if healthy:
            healthy_count += 1
            # Print additional service info if available
            if isinstance(data, dict):
                if "version" in data:
                    print(f"             | Version: {data['version']}")
                if "uptime" in data:
                    print(f"             | Uptime: {data['uptime']}")
        else:
            print(f"             | Error: {data.get('error', 'Unknown error')}")
        
        print("-" * 60)
    
    # Overall status
    print(f"\n📊 OVERALL STATUS: {healthy_count}/{total_count} services healthy")
    
    if healthy_count == total_count:
        print("🎉 All systems operational!")
        return 0
    else:
        print("⚠️  Some services need attention")
        return 1

async def main():
    """Main health check function"""
    print("🔍 Starting health checks...")
    
    try:
        results = await run_health_checks()
        exit_code = print_results(results)
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
