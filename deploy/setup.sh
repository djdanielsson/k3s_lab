#!/bin/bash
python3 -m venv ~/ansible
source ~/ansible/bin/active
pip3 install -r requirements.txt
ansible-galaxy collection install -r collections/requirements.yml