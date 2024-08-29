# k3s_lab
```console
sudo mkdir -p /opt/data/awx/postgres-15
sudo mkdir -p /opt/data/projects
sudo mkdir -p /opt/data/galaxy/postgres-15
sudo mkdir -p /opt/data/galaxy/file
sudo mkdir -p /opt/data/galaxy/redis
sudo mkdir -p /opt/data/git
sudo mkdir -p /opt/data/registry
sudo mkdir -p /opt/data/eda/postgres-13/data
sudo chown 26:0 /opt/data/eda/postgres-13/data
sudo chmod 700 /opt/data/eda/postgres-13/data
sudo chown 1000:0 /opt/data/projects
sudo chown 26:0 /opt/data/awx/postgres-15/data
sudo chown 1000:0 /opt/data/galaxy/file
```