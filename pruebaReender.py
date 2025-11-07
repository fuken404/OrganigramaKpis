import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge 
from streamlit_flow.state import StreamlitFlowState
from streamlit_flow.layouts import TreeLayout
        
nodes = [StreamlitFlowNode(id='1', pos=(0, 0), data={'content': 'Node 1'}, node_type='input', source_position='bottom'),
        StreamlitFlowNode('2', (0, 0), {'content': 'Node 2'}, 'default', 'bottom', 'top'),
        StreamlitFlowNode('3', (0, 0), {'content': 'Node 3'}, 'default', 'bottom', 'top'),
        StreamlitFlowNode('4', (0, 0), {'content': 'Node 4'}, 'output', target_position='top'),
        StreamlitFlowNode('5', (0, 0), {'content': 'Node 5'}, 'output', target_position='top'),
        StreamlitFlowNode('6', (0, 0), {'content': 'Node 6'}, 'output', target_position='top'),
        StreamlitFlowNode('7', (0, 0), {'content': 'Node 7'}, 'output', target_position='top'),]

edges = [StreamlitFlowEdge('1-2', '1', '2', animated=False),
        StreamlitFlowEdge('1-3', '1', '3', animated=False),
        StreamlitFlowEdge('2-4', '2', '4', animated=False),
        StreamlitFlowEdge('2-5', '2', '5', animated=False),
        StreamlitFlowEdge('3-6', '3', '6', animated=False),
        StreamlitFlowEdge('3-7', '3', '7', animated=False),
        ]

if 'flow_state' not in st.session_state:
    st.session_state['flow_state'] = StreamlitFlowState(nodes, edges)

streamlit_flow('tree_layout', st.session_state['flow_state'], layout=TreeLayout(direction='down'), fit_view=True)
