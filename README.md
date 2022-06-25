# projecto-semestral-77036_102477

## How to run daemon.py
```
python3 daemon.py [folder] [id] [node_addr] [node_port] -net_addr [net_addr] -net_port [net_port] --timeout [time] --savelog
```
- **[folder]:** Folder of the node to be started (REQUIRED)
- **[id]:** ID of the node to be started (it is supposed linked to de folder with the images) (REQUIRED)
- **[node_addr]:** Address of the node to be started (REQUIRED)
- **[node_port]:** Port of the node to be started (REQUIRED)
- **-net_addr [net_addr]:** Address of the node in the Network to be contacted for the JOIN_REQUEST
- **-net_port [net_port]:** Port of the node in the Network to be contacted for the JOIN_REQUEST
- **--timeout [time]:** Length of the timeout
- **--savelog:** The logs will appear in the terminal

## How to run client.py
```
python3 client.py [node_addr] [node_port]
```
- **[node_addr]:** Address of the node to be contacted (REQUIRED)
- **[node_port]:** Port of the node to be contacted (REQUIRED)
