"""Performance tests for the Knowledge Graph MCP server."""

import pytest
import asyncio
import time
import statistics
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PerformanceMetrics:
    """Helper class to track and analyze performance metrics."""
    
    def __init__(self):
        self.operation_times: List[float] = []
        
    def add_timing(self, duration: float):
        """Add an operation timing."""
        self.operation_times.append(duration)
    
    def get_stats(self) -> Dict[str, float]:
        """Calculate performance statistics."""
        if not self.operation_times:
            return {}
        
        return {
            "min": min(self.operation_times),
            "max": max(self.operation_times),
            "avg": statistics.mean(self.operation_times),
            "median": statistics.median(self.operation_times),
            "p95": statistics.quantiles(self.operation_times, n=20)[18],  # 95th percentile
            "total_operations": len(self.operation_times),
            "total_time": sum(self.operation_times)
        }

async def measure_operation(operation, *args, **kwargs) -> float:
    """Measure the execution time of an operation."""
    start_time = time.time()
    await operation(*args, **kwargs)
    return time.time() - start_time

@pytest.mark.asyncio
async def test_entity_creation_performance(server, clean_db):
    """Test entity creation performance under load."""
    metrics = PerformanceMetrics()
    
    # Create 100 entities with properties
    async def create_entity(i: int):
        duration = await measure_operation(
            server.handlers.add_entity,
            {
                "type": "test_entity",
                "name": f"Entity{i}",
                "properties": {
                    "index": i,
                    "data": f"test_data_{i}",
                    "timestamp": time.time()
                }
            }
        )
        metrics.add_timing(duration)
    
    # Create entities concurrently in batches of 10
    batch_size = 10
    total_entities = 100
    
    for batch_start in range(0, total_entities, batch_size):
        batch_end = min(batch_start + batch_size, total_entities)
        await asyncio.gather(*[
            create_entity(i) for i in range(batch_start, batch_end)
        ])
    
    # Log performance stats
    stats = metrics.get_stats()
    logger.info("Entity Creation Performance:")
    logger.info(f"Total entities: {stats['total_operations']}")
    logger.info(f"Total time: {stats['total_time']:.2f}s")
    logger.info(f"Average time per entity: {stats['avg']:.3f}s")
    logger.info(f"95th percentile: {stats['p95']:.3f}s")
    
    # Performance assertions
    assert stats["avg"] < 0.1  # Average creation time should be under 100ms
    assert stats["p95"] < 0.2  # 95% of operations should be under 200ms

@pytest.mark.asyncio
async def test_query_performance(server, clean_db):
    """Test query performance with a large dataset."""
    # Setup test data
    entity_count = 1000
    
    # Create test entities
    entities = []
    for i in range(entity_count):
        result = await server.handlers.add_entity({
            "type": "performance_test",
            "name": f"TestEntity{i}",
            "properties": {
                "group": f"group_{i % 10}",
                "value": i
            }
        })
        entities.append(result["id"])
    
    # Test search performance
    metrics = PerformanceMetrics()
    
    # Perform different types of searches
    search_tests = [
        ("Simple property search", {
            "properties": {"group": "group_1"}
        }),
        ("Multi-property search", {
            "type": "performance_test",
            "properties": {
                "group": "group_2",
                "value": 2
            }
        }),
        ("Type-only search", {
            "type": "performance_test"
        })
    ]
    
    for test_name, search_params in search_tests:
        duration = await measure_operation(
            server.handlers.search_entities,
            search_params
        )
        metrics.add_timing(duration)
        logger.info(f"{test_name} took {duration:.3f}s")
    
    stats = metrics.get_stats()
    assert stats["avg"] < 0.5  # Average search should be under 500ms

@pytest.mark.asyncio
async def test_relationship_performance(server, clean_db):
    """Test relationship operations performance."""
    metrics = PerformanceMetrics()
    
    # Create test entities
    entity_count = 100
    entities = []
    for i in range(entity_count):
        result = await server.handlers.add_entity({
            "type": "node",
            "name": f"Node{i}"
        })
        entities.append(result["id"])
    
    # Create relationships between entities
    async def create_relationship(source_idx: int, target_idx: int):
        duration = await measure_operation(
            server.handlers.add_relationship,
            {
                "source_id": entities[source_idx],
                "target_id": entities[target_idx],
                "type": "connected_to",
                "properties": {
                    "weight": source_idx + target_idx
                }
            }
        )
        metrics.add_timing(duration)
    
    # Create a network of relationships
    tasks = []
    for i in range(entity_count):
        # Connect each node to 5 others
        for j in range(5):
            target = (i + j + 1) % entity_count
            tasks.append(create_relationship(i, target))
    
    await asyncio.gather(*tasks)
    
    # Test relationship query performance
    query_metrics = PerformanceMetrics()
    
    # Query relationships for each entity
    for entity_id in entities[:10]:  # Test with first 10 entities
        duration = await measure_operation(
            server.handlers.get_relationships,
            {"entity_id": entity_id, "direction": "both"}
        )
        query_metrics.add_timing(duration)
    
    relationship_stats = metrics.get_stats()
    query_stats = query_metrics.get_stats()
    
    logger.info("Relationship Creation Performance:")
    logger.info(f"Average time: {relationship_stats['avg']:.3f}s")
    logger.info("Relationship Query Performance:")
    logger.info(f"Average time: {query_stats['avg']:.3f}s")
    
    # Performance assertions
    assert relationship_stats["avg"] < 0.1  # Creation under 100ms
    assert query_stats["avg"] < 0.1  # Queries under 100ms

@pytest.mark.asyncio
async def test_concurrent_mixed_operations(server, clean_db):
    """Test performance under mixed concurrent operations."""
    
    async def random_operation(op_id: int):
        """Perform a random sequence of operations."""
        # Create an entity
        entity_result = await server.handlers.add_entity({
            "type": "concurrent_test",
            "name": f"Entity{op_id}",
            "properties": {"op_id": op_id}
        })
        entity_id = entity_result["id"]
        
        # Update it
        await server.handlers.update_entity({
            "id": entity_id,
            "properties": {
                "op_id": op_id,
                "updated": True
            }
        })
        
        # Search for it
        await server.handlers.search_entities({
            "properties": {"op_id": op_id}
        })
        
        # Delete it
        await server.handlers.delete_entity({"id": entity_id})
    
    # Run multiple operation sequences concurrently
    start_time = time.time()
    await asyncio.gather(*[
        random_operation(i) for i in range(50)
    ])
    total_time = time.time() - start_time
    
    logger.info(f"Mixed operations completed in {total_time:.2f}s")
    assert total_time < 10  # Should complete within 10 seconds
