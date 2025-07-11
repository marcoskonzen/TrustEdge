# Importing EdgeSimPy components
from edge_sim_py.components.edge_server import EdgeServer
from edge_sim_py.components.service import Service
from edge_sim_py.components.user import User
from edge_sim_py.components.application import Application

# Importing native Python modules/packages
from json import dumps

# Importing helper functions
from simulator.helper_functions import *

from simulator.extensions import *

# Calculating reliability metrics

def get_server_total_failures(server):
    """Retorna o número total de falhas de um servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        int: Número total de falhas registradas.
    """
    history = server.failure_model.failure_history
    return len(history)


def get_server_mttr(server):
    """Calcula o Mean Time To Repair (MTTR) do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo médio para reparo (MTTR) ou 0 se não houver falhas.
    """
    history = server.failure_model.failure_history
    repair_times = []
    for failure_occurrence in history:
        repair_times.append(failure_occurrence["becomes_available_at"] - failure_occurrence["failure_starts_at"])

    return sum(repair_times) / len(repair_times) if repair_times else 0


def get_server_uptime(server):
    """Calcula o tempo total de atividade do servidor durante a simulação.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de atividade (uptime) do servidor durante a simulação.
    """
    current_step = server.model.schedule.steps + 1
    
    # O uptime é o tempo total da simulação menos o downtime
    total_downtime = get_server_downtime(server=server)
    total_uptime = current_step - total_downtime
    
    return total_uptime


def get_server_mtbf(server):
    """Calcula o Mean Time Between Failures (MTBF) do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo médio entre falhas (MTBF) ou infinito se não houver falhas.
    """
    number_of_failures = len(server.failure_model.failure_history)
    
    if number_of_failures == 0:
        return float("inf")  # Retorna infinito se não houver falhas
        
    return get_server_uptime(server) / number_of_failures


def get_server_failure_rate(server):
    """Calcula a taxa de falha do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Taxa de falha (failures/time unit) ou 0 se não houver falhas.
    """
    mtbf = get_server_mtbf(server)
    return 1 / mtbf if mtbf != 0 and mtbf != float("inf") else 0


def get_server_conditional_reliability(server, upcoming_instants):
    """Calcula a confiabilidade condicional do servidor para instantes futuros.
    
    Args:
        server (EdgeServer): O objeto servidor.
        upcoming_instants (int): Número de instantes futuros a considerar.
        
    Returns:
        float: Valor da confiabilidade condicional (entre 0 e 1).
    """
    history = server.failure_model.failure_history
    server_failure_rate = get_server_failure_rate(server)
    
    if server_failure_rate == 0:
        return 1.0  # Confiabilidade máxima se não há taxa de falha
        
    # Usando math.exp para maior precisão nos cálculos exponenciais
    return math.exp(-server_failure_rate * upcoming_instants)


def get_server_downtime(server):
    """Calcula o tempo total de inatividade do servidor durante a simulação.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo total de inatividade (downtime) do servidor durante a simulação.
    """
    current_step = server.model.schedule.steps + 1
    total_downtime = 0
    
    for failure_occurrence in server.failure_model.failure_history:
        # Só considera falhas que aconteceram durante a simulação (início >= 0)
        if failure_occurrence["failure_starts_at"] >= 0 and failure_occurrence["failure_starts_at"] < current_step:
            # Calcula o tempo de falha até o step atual ou até o reparo, o que vier primeiro
            failure_start = failure_occurrence["failure_starts_at"]
            failure_end = min(failure_occurrence["becomes_available_at"], current_step)
            total_downtime += failure_end - failure_start

    return total_downtime


def get_application_downtime(application):
    """Calcula o tempo de downtime da aplicação.
    
    Args:
        application (Application): O objeto aplicação.
        
    Returns:
        int: Número de timesteps onde a aplicação esteve indisponível.
    """
    
    downtime_count = 0
    for availability_status in application.availability_history.availability_status:
        if availability_status is False:
            downtime_count += 1
        
    return downtime_count
    

def get_application_uptime(application):
    """Calcula o tempo de uptime da aplicação.
    
    Args:
        application (Application): O objeto aplicação.
        
    Returns:
        int: Número de timesteps onde a aplicação esteve disponível.
    """
   
    uptime_count = 0
    for availability_status in application.availability_history.availability_status:
        if availability_status is True:
                uptime_count += 1
        
    return uptime_count
    
    
def get_user_perceived_downtime(user, application_id):
    """Calcula o tempo de downtime percebido pelo usuário para uma aplicação específica.
    
    Args:
        user (User): O objeto usuário.
        application_id (str): O ID da aplicação.
        
    Returns:
        int: O número de timesteps onde o usuário percebeu downtime.
    """
    if not hasattr(user, "user_perceived_downtime_history"):
        return 0
        
    if str(application_id) not in user.user_perceived_downtime_history:
        return 0
        
    # Conta os casos onde o usuário percebeu downtime (True nos registros)
    perceived_downtime = sum(1 for status in user.user_perceived_downtime_history[str(application_id)] if status)
    return perceived_downtime

def display_simulation_metrics(simulation_parameters: dict):
    # Métricas detalhadas de servidor (uptime, downtime, MTBF, taxa de falhas, confiabilidade e trust score)
    server_metrics = {}
    for server in EdgeServer.all():
        # Calcula a confiabilidade instantânea para o próximo instante (t=1)
        reliability = get_server_conditional_reliability(server, upcoming_instants=1)
        trust_score = get_server_trust_score(server)
        time_since_repair = get_time_since_last_repair(server)
        
        server_metrics[f"Server {server.id}"] = {
            "Risk Score": trust_score,
            "Uptime": get_server_uptime(server),
            "Downtime": get_server_downtime(server),
            "MTBF": get_server_mtbf(server),
            "MTTR": get_server_mttr(server),
            "Failure Rate": get_server_failure_rate(server),
            "Reliability": reliability,
            "Time Since Last Repair": time_since_repair,
            "Total Failures": get_server_total_failures(server)
        }
    
    # Métricas detalhadas de aplicações (uptime e downtime de cada aplicação)
    application_metrics = {}
    for application in Application.all():
        application_metrics[f"Application {application.id}"] = {
            "Uptime": get_application_uptime(application),
            "Downtime": get_application_downtime(application)
        }
    
    # Métricas detalhadas de usuários (downtime percebido por cada usuário para cada aplicação)
    user_metrics = {}
    for user in User.all():
        user_entry = {}
        for application in user.applications:
            perceived_downtime = get_user_perceived_downtime(user, application.id)
            user_entry[f"Application {application.id} Perceived Downtime"] = perceived_downtime
        user_metrics[f"User {user.id}"] = user_entry

        
    # # Calcular disponibilidade das aplicações
    # all_apps = list(Application.all())
    # app_availability = {}
    # for app in all_apps:
    #     uptime = get_application_uptime(app)
    #     downtime = get_application_downtime(app)
    #     # Calculamos a disponibilidade como a proporção de tempo em que a aplicação esteve disponível
    #     # Se não houver dados de uptime ou downtime, consideramos disponibilidade de 100%
    #     app_availability[f"Application {app.id}"] = f"{(uptime / (uptime + downtime)) * 100:.2f}%" if (uptime + downtime) > 0 else 1.0

    metrics = {
        "Simulation Parameters": simulation_parameters,
        #"Execution Time (seconds)": round(simulation_execution_time, 2),
        "Number of Applications/Services/Users": f"{Application.count()}/{Service.count()}/{User.count()}",
        #"Application Availability": app_availability,
        "Server Metrics": server_metrics,
        "Application Metrics": application_metrics,
        "User Perceived Downtime Metrics": user_metrics,
    }
    
    print_application_info()
    
    print(dumps(metrics, indent=4))

def display_reliability_metrics():
    """Exibe um resumo das métricas de confiabilidade de todos os servidores.
    Esta função é útil para análises durante a execução da simulação.
    
    Os servidores são ordenados por score de risco (crescente), 
    onde valores menores indicam servidores mais confiáveis.
    
    O score de risco é calculado como: taxa_falha * (tempo_desde_reparo/MTBF)
    Quanto mais próximo o servidor estiver de seu tempo médio entre falhas,
    maior será seu score de risco.
    """
    print("\n\n")
    print("==========================================================================")
    print("================= MÉTRICAS DE CONFIABILIDADE DOS SERVIDORES ==============")
    print("==========================================================================")
    
    # Ordenar por score de risco (crescente) - servidores mais confiáveis primeiro (menor score)
    servers = sorted(EdgeServer.all(), key=lambda s: get_server_trust_score(s))
    
    # Cabeçalho da tabela
    print(f"{'Rank':^5}|{'ID':^5}|{'Score Risco':^12}|{'Taxa Falha':^12}|{'T.Últ.Rep':^10}|{'MTBF':^10}|{'MTTR':^8}|{'Falhas':^8}")
    print(f"{'':^5}|{'':^5}|{'(F×T/MTBF)':^12}|{'':^12}|{'':^10}|{'':^10}|{'':^8}|{'':^8}")
    print("-" * 78)
    
    for rank, server in enumerate(servers, 1):
        server_id = server.id
        failures = get_server_total_failures(server)
        mttr = get_server_mttr(server)
        mtbf = get_server_mtbf(server)
        risk_score = get_server_trust_score(server)
        time_since_repair = get_time_since_last_repair(server)
        failure_rate = get_server_failure_rate(server)
        
        # Formatação especial para MTBF e tempo desde último reparo infinito
        if mtbf == float("inf"):
            mtbf_str = "∞"
        else:
            mtbf_str = f"{mtbf:.2f}"
            
        if time_since_repair == float("inf"):
            time_repair_str = "Nunca"
        else:
            time_repair_str = f"{time_since_repair:.0f}"
        
        # Formatação especial para risk score
        if risk_score == 0:
            risk_score_str = "Mínimo"
        else:
            risk_score_str = f"{risk_score:.4f}"
        
        print(f"{rank:^5}|{server_id:^5}|{risk_score_str:^12}|{failure_rate:^12.6f}|{time_repair_str:^10}|{mtbf_str:^10}|{mttr:^8.2f}|{failures:^8}")
    
def get_time_since_last_repair(server):
    """Calcula o tempo desde o último reparo do servidor.
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Tempo desde o último reparo ou infinito se não houver falhas.
    """
    if not server.failure_model.failure_history:
        return float("inf")  # Nunca falhou, então o tempo é "infinito"
    
    current_step = server.model.schedule.steps
    
    # Ordena o histórico de falhas pelo timestamp de início da falha (decrescente)
    sorted_history = sorted(
        server.failure_model.failure_history, 
        key=lambda x: x["failure_starts_at"], 
        reverse=True
    )
    
    # Pega a falha mais recente
    last_failure = sorted_history[0]
    
    # Calcula o tempo desde o último reparo
    time_since_repair = current_step - last_failure["becomes_available_at"]
    
    # Se o tempo for negativo, significa que o servidor ainda está em reparo
    return max(0, time_since_repair)


def get_server_trust_score(server):
    """Calcula um score de risco instantâneo para o servidor.
    
    O score é calculado multiplicando-se:
    1. Taxa de falhas (quanto maior, pior)
    2. Proporção do tempo desde o último reparo em relação ao MTBF
       (quanto maior essa proporção, maior o risco de uma falha iminente)
    
    Um servidor com menor score de risco é mais confiável porque:
    - Tem menor taxa de falhas historicamente
    - Ainda não se aproximou de seu MTBF desde o último reparo
    
    Args:
        server (EdgeServer): O objeto servidor.
        
    Returns:
        float: Score de risco (quanto menor, melhor - indica maior confiabilidade).
              Servidores que nunca falharam retornam 0 (máxima confiabilidade).
    """
    # Obter os valores dos parâmetros
    failure_rate = get_server_failure_rate(server)
    time_since_repair = get_time_since_last_repair(server)
    mtbf = get_server_mtbf(server)
    
    # Caso especial: servidor nunca falhou
    if time_since_repair == float("inf"):
        # Se o servidor nunca falhou, atribuímos o menor score possível (risco zero)
        return 0
    
    # Caso especial: taxa de falha é zero ou MTBF é infinito
    # (isso pode acontecer se o servidor só falhou uma vez há muito tempo)
    if failure_rate == 0 or mtbf == float("inf"):
        # Atribuímos uma taxa de falha mínima para não zerar a multiplicação
        adjusted_failure_rate = 0.0001  # Um valor muito pequeno
        # E usamos o tempo desde o reparo como base para o cálculo da proporção
        proportion = 0.01  # Uma proporção pequena, mas não zero
    else:
        adjusted_failure_rate = failure_rate
        # Calcular a proporção do tempo desde o último reparo em relação ao MTBF
        proportion = time_since_repair / mtbf
        # Limitar a proporção a um máximo de 2.0 para evitar crescimento excessivo
        proportion = min(proportion, 2.0)
    
    # Cálculo: multiplicar a taxa de falha pela proporção do tempo desde reparo/MTBF
    # Quanto menor o resultado, menor o risco de falha (mais confiável)
    risk_score = adjusted_failure_rate * proportion
    
    return risk_score

def print_application_info():
    """Exibe informações sobre as aplicações, seus servidores de alocação e usuários.
    Esta função mostra a cada passo da simulação onde cada aplicação está alocada
    e quais usuários estão acessando cada aplicação.
    """
    print("\n\n")
    print("==========================================================================")
    print("================= INFORMAÇÕES DE APLICAÇÕES E SERVIDORES =================")
    print("==========================================================================")
    
    print(f"{'Aplicação ID':^12}|{'Servidor ID':^12}|{'Usuário ID':^12}|{'Status':^10}")
    print("-" * 50)
    
    for application in Application.all():
        # Para cada aplicação, encontrar o servidor onde está alocada
        service = application.services[0] if application.services else None
        server_id = service.server.id if service and service.server else "N/A"
        
        # Encontrar os usuários que acessam esta aplicação
        users = application.users
        
        if users:
            # Se houver usuários, mostramos uma linha para cada usuário
            for user in users:
                status = "Online" if application.availability_status else "Offline"
                print(f"{application.id:^12}|{server_id:^12}|{user.id:^12}|{status:^10}")
        else:
            # Se não houver usuários, mostramos apenas a aplicação e o servidor
            status = "Online" if application.availability_status else "Offline"
            print(f"{application.id:^12}|{server_id:^12}|{'N/A':^12}|{status:^10}")

def trust_edge(parameters: dict = {}):  
    """Algoritmo principal que implementa a lógica do TrustEdge.
    
    Args:
        parameters (dict): Parâmetros da simulação.
    """
    display_simulation_metrics(simulation_parameters=parameters)
    display_reliability_metrics()
   
        