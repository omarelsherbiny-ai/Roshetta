"""
LangGraph Multi-Agent Orchestration Layer for Roshetta Pharmacy System.
Coordinates Intake, Verification, Inventory, Finance, and Safety agents.
"""

from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.agents.intake import intake_agent
from agents.agents.verification import verification_agent
from agents.agents.finance import finance_agent
from agents.agents.inventory import inventory_agent


def route_intent(state: AgentState) -> str:
    """Routing function after intake analysis."""
    intent = state.get("intent", "general_chat")
    if intent in ["log_sale", "log_expense", "log_restock"]:
        return "verification"
    elif intent == "query_finance":
        return "finance"
    elif intent == "query_stock":
        return "inventory"
    return "end"


def build_orchestrator():
    """Builds and compiles the LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # Add Nodes
    graph.add_node("intake", intake_agent)
    graph.add_node("verification", verification_agent)
    graph.add_node("finance", finance_agent)
    graph.add_node("inventory", inventory_agent)

    # Set Entry Point
    graph.set_entry_point("intake")

    # Add Conditional Edges
    graph.add_conditional_edges(
        "intake",
        route_intent,
        {
            "verification": "verification",
            "finance": "finance",
            "inventory": "inventory",
            "end": END,
        }
    )

    # Terminal transitions
    graph.add_edge("verification", END)
    graph.add_edge("finance", END)
    graph.add_edge("inventory", END)

    return graph.compile()


# Compiled singleton runner
roshetta_graph = build_orchestrator()


async def run_orchestration(initial_state: AgentState) -> AgentState:
    """Async runner for the LangGraph agent workflow."""
    return await roshetta_graph.ainvoke(initial_state)
