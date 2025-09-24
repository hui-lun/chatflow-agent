import logging
from langgraph.graph import StateGraph, END

from .nodes import (
    AgentState,
    select_tool,
    spec_search_node,
    recommend_node,
    gen_l10_node,
)

logger = logging.getLogger(__name__)

graph = StateGraph(AgentState)

graph.add_node("select_tool", select_tool)
graph.add_node("spec_search_node", spec_search_node)
graph.add_node("recommend_node", recommend_node)
graph.add_node("gen_l10_node", gen_l10_node)

graph.set_entry_point("select_tool")

# 從 select_tool 到其他節點的條件邊緣
graph.add_conditional_edges(
    "select_tool",
    lambda state: state["next_node"],
    {
        "spec_search_node": "spec_search_node",
        "recommend_node": "recommend_node",
    }
)

# spec_search_node 直接結束
graph.add_edge("spec_search_node", END)

# recommend_node 根據條件判斷下一步
graph.add_conditional_edges(
    "recommend_node",
    lambda state: state["next_node"],
    {
        "gen_l10_node": "gen_l10_node",
        "END": END,
    }
)

# gen_l10_node 直接結束
graph.add_edge("gen_l10_node", END)

# Compile the graph with checkpointing

app = graph.compile()