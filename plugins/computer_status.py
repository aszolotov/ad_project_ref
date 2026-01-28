# Plugin: Computer Status Checker
# Description: Adds 'status' field to computer list by pinging hosts

def get_metadata():
    return {
        "name": "Computer Status Checker",
        "version": "1.0",
        "author": "System",
        "description": "Checks online status of computers via ICMP Ping"
    }

def check_status(computers):
    """
    Хук для обогащения списка компьютеров статусом Online/Offline.
    Принимает список словарей компьютеров.
    """
    # Ограничим количество пингов за раз, чтобы не ждать вечность
    # В реальном проекте это должно быть асинхронно или кэшироваться
    max_check = 20 
    
    for i, comp in enumerate(computers):
        if i >= max_check:
            comp["status"] = "Unknown (Limit Reached)"
            continue
            
        host = comp.get("dNSHostName") or comp.get("name")
        if host:
            is_online = network_tools.ping(host, timeout=1)
            comp["status"] = "Online" if is_online else "Offline"
        else:
            comp["status"] = "Unknown"
            
    return computers

def register(manager):
    manager.register_hook("enrich_computers", check_status)
