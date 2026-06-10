#!/bin/bash
python agent_api.py &
streamlit run web/app.py --server.port=8080 --server.address=0.0.0.0
