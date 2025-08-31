#!/usr/bin/env python3

import asyncio
import aiohttp
import sys
from typing import Dict, List

# Service health check endpoints
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

async def check_service_health(session: aiohttp.ClientSession, name: str, url: str) -> Dict:
    """Check health of a single service"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status == 200:
                data = await response.json()
                return {"service": name, "status": "healthy", "details": data}
            else:
                return {"service": name, "status": "unhealthy", "error": f"HTTP {response.status}"}
    except Exception as e:
        return {"service": name, "status": "unhealthy", "error": str(e)}

async def check_all_services() -> List[Dict]:
    """Check health of all services"""
    async with aiohttp.ClientSession() as session:
        tasks = [check_service_health(session, name, url) for name, url in SERVICES.items()]
        return await asyncio.gather(*tasks)

def main():
    """Main health check function"""
    results = asyncio.run(check_all_services())
    
    healthy_count = sum(1 for r in results if r["status"] == "healthy")
    total_count = len(results)
    
    print(f"Health Check Results ({healthy_count}/{total_count} healthy)")
    print("=" * 50)
    
    for result in results:
        status_icon = "✅" if result["status"] == "healthy" else "❌"
        print(f"{status_icon} {result['service']}: {result['status']}")
        if result["status"] == "unhealthy":
            print(f"   Error: {result['error']}")
    
    # Exit with error code if any service is unhealthy
    if healthy_count < total_count:
        sys.exit(1)
    else:
        print("\n🎉 All services are healthy!")
        sys.exit(0)

if __name__ == "__main__":
    main()
