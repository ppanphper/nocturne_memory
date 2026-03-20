"""
End-to-end integration test: MCP tools with namespace isolation.

Verifies that all 7 MCP tools work correctly through the mcp_server layer
and that namespace isolation is enforced at every operation.
"""

import os
import sys
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["SKIP_DB_INIT"] = "true"
os.environ["VALID_DOMAINS"] = "core,writer,game,notes,system"
os.environ["CORE_MEMORY_URIS"] = "core://agent,core://my_user"

from db.namespace import set_namespace
from db.database import DatabaseManager
from db.graph import GraphService
from db.search import SearchIndexer
from db.glossary import GlossaryService
import db as db_pkg


@pytest_asyncio.fixture
async def mcp_env():
    """Set up a fresh in-memory DB and patch the global service singletons."""
    _db = DatabaseManager("sqlite+aiosqlite://")
    await _db.init_db()
    _search = SearchIndexer(_db)
    _glossary = GlossaryService(_db, _search)
    _graph = GraphService(_db, _search)

    old = (db_pkg._db_manager, db_pkg._graph_service, db_pkg._search_indexer, db_pkg._glossary_service)
    db_pkg._db_manager = _db
    db_pkg._graph_service = _graph
    db_pkg._search_indexer = _search
    db_pkg._glossary_service = _glossary

    yield

    db_pkg._db_manager, db_pkg._graph_service, db_pkg._search_indexer, db_pkg._glossary_service = old
    await _db.close()


@pytest.mark.asyncio
async def test_full_mcp_flow_with_namespace_isolation(mcp_env):
    """Simulate two agents calling all 7 MCP tools through the server layer."""
    from mcp_server import (
        read_memory, create_memory, update_memory,
        delete_memory, add_alias, manage_triggers, search_memory,
    )

    # ============================================================
    # Agent A: create memories
    # ============================================================
    set_namespace("agent_a")

    result = await create_memory(
        parent_uri="core://",
        content="I am Agent A's identity.",
        priority=0,
        title="agent",
        disclosure="When asking who I am",
    )
    assert "Success" in result
    assert "core://agent" in result

    result = await create_memory(
        parent_uri="core://agent",
        content="Agent A met User on 2026-01-01.",
        priority=1,
        title="my_user",
        disclosure="When talking about my user",
    )
    assert "Success" in result

    # ============================================================
    # Agent B: create same URI structure, different content
    # ============================================================
    set_namespace("agent_b")

    result = await create_memory(
        parent_uri="core://",
        content="I am Agent B's identity.",
        priority=0,
        title="agent",
        disclosure="When asking who I am",
    )
    assert "Success" in result

    # ============================================================
    # Verify read isolation
    # ============================================================
    set_namespace("agent_a")
    content_a = await read_memory("core://agent")
    assert "Agent A" in content_a
    assert "Agent B" not in content_a

    set_namespace("agent_b")
    content_b = await read_memory("core://agent")
    assert "Agent B" in content_b
    assert "Agent A" not in content_b

    # ============================================================
    # Verify system://index isolation
    # ============================================================
    set_namespace("agent_a")
    index_a = await read_memory("system://index")
    assert "my_user" in index_a

    set_namespace("agent_b")
    index_b = await read_memory("system://index")
    assert "my_user" not in index_b

    # ============================================================
    # Verify system://recent isolation
    # ============================================================
    set_namespace("agent_a")
    recent_a = await read_memory("system://recent")
    assert "core://agent" in recent_a

    set_namespace("agent_b")
    recent_b = await read_memory("system://recent")
    lines_b = [l for l in recent_b.split("\n") if l.strip().startswith("1.")]
    assert any("core://agent" in l for l in lines_b)
    assert not any("my_user" in l for l in lines_b)

    # ============================================================
    # Verify search isolation
    # ============================================================
    set_namespace("agent_a")
    search_a = await search_memory("identity")
    assert "Agent A" in search_a
    assert "Agent B" not in search_a

    set_namespace("agent_b")
    search_b = await search_memory("identity")
    assert "Agent B" in search_b
    assert "Agent A" not in search_b

    # ============================================================
    # Verify update isolation
    # ============================================================
    set_namespace("agent_a")
    result = await update_memory(
        "core://agent",
        old_string="I am Agent A's identity.",
        new_string="I am Agent A's evolved identity.",
    )
    assert "Success" in result

    content_a_updated = await read_memory("core://agent")
    assert "evolved" in content_a_updated

    set_namespace("agent_b")
    content_b_unchanged = await read_memory("core://agent")
    assert "evolved" not in content_b_unchanged
    assert "Agent B" in content_b_unchanged

    # ============================================================
    # Verify add_alias isolation
    # ============================================================
    set_namespace("agent_a")
    result = await add_alias(
        new_uri="writer://agent_copy",
        target_uri="core://agent",
        priority=5,
    )
    assert "Success" in result

    set_namespace("agent_b")
    read_alias_b = await read_memory("writer://agent_copy")
    assert "Error" in read_alias_b or "not found" in read_alias_b

    # ============================================================
    # Verify manage_triggers isolation
    # ============================================================
    set_namespace("agent_a")
    result = await manage_triggers("core://agent", add=["identity_trigger"])
    assert "Added" in result

    set_namespace("agent_a")
    glossary_a = await read_memory("system://glossary")
    assert "identity_trigger" in glossary_a

    # ============================================================
    # Verify delete isolation
    # ============================================================
    set_namespace("agent_a")
    result = await delete_memory("core://agent/my_user")
    assert "Success" in result

    set_namespace("agent_a")
    deleted_read = await read_memory("core://agent/my_user")
    assert "Error" in deleted_read or "not found" in deleted_read

    set_namespace("agent_b")
    content_b_still = await read_memory("core://agent")
    assert "Agent B" in content_b_still

    print("All MCP namespace isolation checks passed!")
