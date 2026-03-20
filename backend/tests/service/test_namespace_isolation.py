"""
Tests for namespace isolation: two agents using different namespaces
should have completely independent memory spaces.
"""

import pytest
import pytest_asyncio

from db.namespace import set_namespace, get_namespace
from db.database import DatabaseManager
from db.graph import GraphService
from db.search import SearchIndexer
from db.glossary import GlossaryService


@pytest_asyncio.fixture
async def services():
    """Spin up an in-memory SQLite database with fresh schema."""
    db = DatabaseManager("sqlite+aiosqlite://")
    await db.init_db()
    search = SearchIndexer(db)
    glossary = GlossaryService(db, search)
    graph = GraphService(db, search)
    yield graph, search, glossary
    await db.close()


@pytest.mark.asyncio
async def test_namespace_isolation_basic(services):
    """Two agents (ns_a, ns_b) create the same URI without conflict."""
    graph, search, _ = services

    # Agent A creates core://agent
    set_namespace("ns_a")
    result_a = await graph.create_memory(
        parent_path="",
        content="I am Agent A.",
        priority=0,
        title="agent",
        domain="core",
    )
    assert result_a["uri"] == "core://agent"

    # Agent B creates core://agent (same URI, different namespace)
    set_namespace("ns_b")
    result_b = await graph.create_memory(
        parent_path="",
        content="I am Agent B.",
        priority=0,
        title="agent",
        domain="core",
    )
    assert result_b["uri"] == "core://agent"

    # Agent A can only read its own memory
    set_namespace("ns_a")
    mem_a = await graph.get_memory_by_path("agent", "core")
    assert mem_a is not None
    assert mem_a["content"] == "I am Agent A."

    # Agent B can only read its own memory
    set_namespace("ns_b")
    mem_b = await graph.get_memory_by_path("agent", "core")
    assert mem_b is not None
    assert mem_b["content"] == "I am Agent B."

    # Verify different node UUIDs (independent entities)
    assert result_a["node_uuid"] != result_b["node_uuid"]


@pytest.mark.asyncio
async def test_namespace_isolation_index(services):
    """get_all_paths only returns paths from the current namespace."""
    graph, _, _ = services

    set_namespace("ns_x")
    await graph.create_memory("", "X content", 0, title="x_mem", domain="core")

    set_namespace("ns_y")
    await graph.create_memory("", "Y content", 0, title="y_mem", domain="core")

    set_namespace("ns_x")
    paths_x = await graph.get_all_paths()
    assert len(paths_x) == 1
    assert paths_x[0]["path"] == "x_mem"

    set_namespace("ns_y")
    paths_y = await graph.get_all_paths()
    assert len(paths_y) == 1
    assert paths_y[0]["path"] == "y_mem"


@pytest.mark.asyncio
async def test_namespace_isolation_search(services):
    """search() only returns results from the current namespace."""
    graph, search, _ = services

    set_namespace("ns_alpha")
    await graph.create_memory(
        "", "The secret alpha protocol", 0, title="alpha_secret", domain="core"
    )

    set_namespace("ns_beta")
    await graph.create_memory(
        "", "The secret beta protocol", 0, title="beta_secret", domain="core"
    )

    set_namespace("ns_alpha")
    results = await search.search("secret")
    assert len(results) == 1
    assert "alpha" in results[0]["uri"]

    set_namespace("ns_beta")
    results = await search.search("secret")
    assert len(results) == 1
    assert "beta" in results[0]["uri"]


@pytest.mark.asyncio
async def test_namespace_isolation_recent(services):
    """get_recent_memories only returns memories from the current namespace."""
    graph, _, _ = services

    set_namespace("ns_one")
    await graph.create_memory("", "Content one", 0, title="one", domain="core")

    set_namespace("ns_two")
    await graph.create_memory("", "Content two", 0, title="two", domain="core")

    set_namespace("ns_one")
    recent = await graph.get_recent_memories(limit=10)
    assert len(recent) == 1
    assert "one" in recent[0]["uri"]


@pytest.mark.asyncio
async def test_namespace_isolation_delete(services):
    """Deleting a path in one namespace does not affect another."""
    graph, _, _ = services

    set_namespace("ns_del_a")
    await graph.create_memory("", "A data", 0, title="shared_name", domain="core")

    set_namespace("ns_del_b")
    await graph.create_memory("", "B data", 0, title="shared_name", domain="core")

    # Delete in namespace A
    set_namespace("ns_del_a")
    await graph.remove_path("shared_name", "core")

    # A sees nothing
    mem_a = await graph.get_memory_by_path("shared_name", "core")
    assert mem_a is None

    # B is unaffected
    set_namespace("ns_del_b")
    mem_b = await graph.get_memory_by_path("shared_name", "core")
    assert mem_b is not None
    assert mem_b["content"] == "B data"


@pytest.mark.asyncio
async def test_default_namespace_backward_compat(services):
    """Default namespace (empty string) works for non-namespaced deployments."""
    graph, _, _ = services

    set_namespace("")
    result = await graph.create_memory(
        "", "Default namespace content", 0, title="default_mem", domain="core"
    )
    assert result["uri"] == "core://default_mem"

    mem = await graph.get_memory_by_path("default_mem", "core")
    assert mem is not None
    assert mem["content"] == "Default namespace content"
