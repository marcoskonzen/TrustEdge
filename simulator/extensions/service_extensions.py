# EdgeSimPy components
from edge_sim_py.components import *
#from simulator.algorithms.trust_edge_v3 import add_to_waiting_queue

# Python libraries
import networkx as nx

def service_step(self):
    """Method that executes the events involving the object at each time step."""

    if len(self._Service__migrations) > 0 and self._Service__migrations[-1]["end"] == None:
        migration = self._Service__migrations[-1]

        # ✅ INICIALIZAR contador se não existir
        if "interrupted_time" not in migration:
            migration["interrupted_time"] = 0

        # ✅ USAR origin/target que provision() criou
        origin = migration.get("origin")
        target = migration.get("target")
        
        relationships_created_by_algorithm = migration.get("relationships_created_by_algorithm", False)
        if origin is None:
            migration_reason = "Provision"
        else:
            migration_reason = migration.get("migration_reason", "unknown")
        
        # ✅ DEBUG
        current_step = self.model.schedule.steps + 1
        
        origin_id_debug = origin.id if origin else "None"
        target_id_debug = target.id if target else "None"
        origin_available = origin.available if origin else "N/A"
        target_available = target.available if target else "N/A"
        
        print(f"\n[SERVICE_STEP] === Serviço {self.id} - Step {current_step} ===")
        print(f"[SERVICE_STEP] migration_reason: '{migration_reason}'")
        print(f"[SERVICE_STEP] origin: {origin_id_debug} (available: {origin_available})")
        print(f"[SERVICE_STEP] target: {target_id_debug} (available: {target_available})")
        print(f"[SERVICE_STEP] Status da migração: {migration.get('status', 'N/A')}")
        
# ✅ DETECÇÃO DE MIGRAÇÃO DE RECUPERAÇÃO
        is_recovery_migration = (migration_reason == "server_failed")
        
        print(f"[SERVICE_STEP] is_recovery_migration: {is_recovery_migration}")
        print()
        
        # ✅ DEBUG: Validar consistência (COM SUPORTE A LIVE MIGRATION)
        if relationships_created_by_algorithm:
            server_id = self.server.id if self.server else None
            
            # Lógica de Live Migration:
            # Se estamos baixando camadas (waiting/pulling) E a origem está viva,
            # o serviço deve permanecer na origem.
            # Caso contrário (download acabou, origem falhou, ou provisionamento), vai para o target.
            is_downloading = migration.get("status") in ["waiting", "pulling_layers"]
            should_be_on_origin = is_downloading and origin is not None and origin.available
            
            expected_server = origin if should_be_on_origin else target
            expected_id_debug = expected_server.id if expected_server else "None"

            if self.server != expected_server:
                print(f"[SERVICE_STEP] ⚠️ INCONSISTÊNCIA: service.server={server_id}, esperado={expected_id_debug}")
                print(f"              Status: {migration.get('status')} | Live Migration: {should_be_on_origin}")
                print(f"              Corrigindo automaticamente...")
                
                self.server = expected_server
                if expected_server and self not in expected_server.services:
                    expected_server.services.append(self)
                
                # Limpeza extra para evitar duplicidade (remove do servidor onde NÃO deveria estar)
                other_server = target if should_be_on_origin else origin
                if other_server and self in other_server.services:
                    other_server.services.remove(self)
        
        # ═══════════════════════════════════════════════════════════════
        # ✅ REMOVER DETECÇÃO DE FALHA AQUI - edge_server_step() já cuida
        # ═══════════════════════════════════════════════════════════════
        
        # Caso 2: Usuário parou de acessar (só verificar se NÃO é recuperação)
        if not is_recovery_migration:
            app = self.application
            user = app.users[0] if app.users else None
            
            if user:
                app_id = str(app.id)
                current_step = self.model.schedule.steps + 1
                
                if app_id in user.access_patterns and user.access_patterns[app_id].history:
                    last_access = user.access_patterns[app_id].history[-1]
                    is_accessing = (last_access["start"] <= current_step <= last_access["end"])
                    
                    if not is_accessing:
                        print(f"[SERVICE_STEP] Usuário parou de acessar - cancelando migração")
                        migration["status"] = "interrupted"
                        migration["end"] = self.model.schedule.steps + 1
                        migration["interruption_reason"] = "user_stopped_accessing"
                        
                        # ✅ INCREMENTAR TEMPO DE INTERRUPÇÃO
                        migration["interrupted_time"] += 1
                        
                        # Limpar do destino
                        if self in target.services:
                            target.services.remove(self)
                        
                        # Limpar da origem
                        if origin and self in origin.services:
                            origin.services.remove(self)
                        
                        # Liberar recursos
                        if self.server:
                            self.server.cpu_demand -= self.cpu_demand
                            self.server.memory_demand -= self.memory_demand
                        
                        self.server = None
                        self._available = False
                        
                        return

        # ✅ PROCESSAMENTO NORMAL DE MIGRAÇÃO (incluindo recuperações)
        image = ContainerImage.find_by(attribute_name="digest", attribute_value=self.image_digest)
        
        layers_downloaded = [l for l in target.container_layers if l.digest in image.layers_digests]
        layers_on_download_queue = [
            flow.metadata["object"]
            for flow in target.download_queue
            if flow.metadata["object"].digest in image.layers_digests
        ]
        
        # ✅ DIAGNÓSTICO: Verificar também waiting_queue
        layers_in_waiting_queue = [
            layer for layer in target.waiting_queue
            if layer.digest in image.layers_digests
        ]
        
        # ✅ DEBUG EXPANDIDO
        if migration["status"] == "waiting" or migration["status"] == "pulling_layers":
            total_needed = len(image.layers_digests)
            total_downloaded = len(layers_downloaded)
            total_downloading = len(layers_on_download_queue)
            total_waiting = len(layers_in_waiting_queue)
            total_accounted = total_downloaded + total_downloading + total_waiting
            
            # ✅ VERIFICAR LIMITE DE DOWNLOADS NO SERVIDOR
            total_downloads_on_server = len(target.download_queue)
            
            # Determinar se deve fazer log (SEMPRE para recuperações)
            pulling_time = migration.get("pulling_layers_time", 0)
            should_log = (
                is_recovery_migration or  # ← SEMPRE logar recuperações
                total_accounted < total_needed or  # Faltam camadas
                (migration["status"] == "pulling_layers") or  # A cada step
                (migration["status"] == "waiting" and total_downloading > 0)  # Transitando para pulling
            )
            
            if should_log:
                print()
                print(f"[SERVICE_STEP] Serviço {self.id} - Status: {migration['status']}")
                
                # ✅ USAR IDs SEGUROS
                if is_recovery_migration:
                    print(f"              🔄 MIGRAÇÃO DE RECUPERAÇÃO")
                    print(f"              Origem {origin_id_debug} (FALHOU) → Destino {target_id_debug}")
                
                print(f"              Alocado no servidor: {target_id_debug}")
                print(f"              Camadas do serviço: {total_needed}")
                print(f"              ✓ Baixadas: {total_downloaded}")
                print(f"              ⏳ Baixando: {total_downloading}")
                print(f"              ⏸ Aguardando: {total_waiting}")
                
                # ✅ INFORMAÇÃO SOBRE O SERVIDOR
                print(f"              Servidor {target_id_debug}:")
                print(f"                - Downloads totais ativos: {total_downloads_on_server}")
                print(f"                - Waiting queue total: {len(target.waiting_queue)}")

                # ✅ MOSTRAR DE ONDE cada camada está sendo baixada
                if total_downloading > 0:
                    print(f"              Detalhes dos downloads:")
                    for flow in target.download_queue:
                        if flow.metadata["object"].digest in image.layers_digests:
                            layer = flow.metadata["object"]
                            source_server = flow.source if hasattr(flow, 'source') else None
                            source_id = source_server.id if source_server else "Unknown"
                            
                            # Identificar tipo de servidor (Registry ou Edge Server)
                            source_type = "Unknown"
                            if source_server:
                                # Verificar se é um Container Registry
                                registries = ContainerRegistry.all()
                                is_registry = any(
                                    hasattr(reg, 'server') and reg.server and reg.server.id == source_server.id 
                                    for reg in registries
                                )
                                source_type = "Registry" if is_registry else "Edge Server"
                            
                            print(f"                - Camada {layer.digest} - Size {layer.size} bytes - From {source_type} {source_id}")

        # ✅ TRANSIÇÃO: waiting → pulling_layers
        if migration["status"] == "waiting":
            layers_on_target_server = layers_downloaded + layers_on_download_queue
            if len(layers_on_target_server) > 0:
                migration["status"] = "pulling_layers"
                print(f"[SERVICE_STEP] Serviço {self.id}: Iniciando download de camadas")
                print(f"              {len(layers_downloaded)} já no servidor, {len(layers_on_download_queue)} baixando")

        # ✅ TRANSIÇÃO: pulling_layers → finished
        if migration["status"] == "pulling_layers" and len(image.layers_digests) == len(layers_downloaded):
            print(f"[SERVICE_STEP] Serviço {self.id}: ✅ Todas as {len(image.layers_digests)} camadas no servidor!")
            
            # Criar imagem no servidor de destino
            if not any([img.digest == self.image_digest for img in target.container_images]):
                template_image = ContainerImage.find_by(attribute_name="digest", attribute_value=self.image_digest)
                if template_image is None:
                    raise Exception(f"Could not find container image with digest: {self.image_digest}")

                image = ContainerImage()
                image.name = template_image.name
                image.digest = template_image.digest
                image.tag = template_image.tag
                image.architecture = template_image.architecture
                image.layers_digests = template_image.layers_digests
                image.server = target
                target.container_images.append(image)

            # ✅ Liberar recursos da ORIGEM (se existir E estiver disponível)
            if origin and origin.available:
                origin.cpu_demand -= self.cpu_demand
                origin.memory_demand -= self.memory_demand
                print(f"[SERVICE_STEP] Recursos liberados da origem {origin.id}")
            elif is_recovery_migration:
                print(f"[SERVICE_STEP] Origem {origin_id_debug} indisponível - sem recursos para liberar")

            # ✅ Para migrações de recuperação, sempre finalizar sem migrar estado
            if is_recovery_migration or self.state == 0 or origin == None:
                migration["status"] = "finished"
                print(f"[SERVICE_STEP] Serviço {self.id}: Finalizando (sem estado para migrar)")
            else:
                migration["status"] = "migrating_service_state"
                self._available = False
                print(f"[SERVICE_STEP] Serviço {self.id}: Iniciando migração de estado ({self.state} bytes)")
                
                path = nx.shortest_path(
                    G=self.model.topology,
                    source=origin.base_station.network_switch,
                    target=target.base_station.network_switch,
                )
                flow = NetworkFlow(
                    topology=self.model.topology,
                    source=origin,
                    target=target,
                    start=self.model.schedule.steps + 1,
                    path=path,
                    data_to_transfer=self.state,
                    metadata={"type": "service_state", "object": self},
                )
                self.model.initialize_agent(agent=flow)

        # Incrementar contadores
        if migration["status"] == "waiting":
            migration["waiting_time"] += 1
        elif migration["status"] == "pulling_layers":
            migration["pulling_layers_time"] += 1
        elif migration["status"] == "migrating_service_state":
            migration["migrating_service_state_time"] += 1

        # ✅ FINALIZAÇÃO
        if migration["status"] == "finished":
            migration["end"] = self.model.schedule.steps + 1
            print(f"[SERVICE_STEP] Serviço {self.id}: Migração FINALIZADA")
            print(f"              Origin: {origin.id if origin else 'None'}, Target: {target.id}")
            
            if is_recovery_migration:
                print(f"              🔄 Recuperação de falha concluída")

            if relationships_created_by_algorithm:
                # ✅ Algoritmo já criou relacionamentos - apenas limpar origem
                if origin and origin.available and self in origin.services:
                    origin.services.remove(self)
                    print(f"[SERVICE_STEP] ✓ Removido da origem {origin.id}")
                
                # Validar consistência
                if self.server != target:
                    print(f"[SERVICE_STEP] ⚠️ Corrigindo: service.server={self.server.id if self.server else None} → {target.id}")
                    self.server = target
                
                if self not in target.services:
                    print(f"[SERVICE_STEP] ⚠️ Adicionando ao destino {target.id}")
                    target.services.append(self)
            else:
                # ✅ EdgeSimPy gerencia relacionamentos
                if self.server and self in self.server.services:
                    self.server.services.remove(self)
                
                self.server = target
                if self not in target.services:
                    target.services.append(self)
            
            # Decrementar contadores
            if origin and hasattr(origin, 'ongoing_migrations'):
                origin.ongoing_migrations = max(0, origin.ongoing_migrations - 1)
            if hasattr(target, 'ongoing_migrations'):
                target.ongoing_migrations = max(0, target.ongoing_migrations - 1)

            # ✅ MARCAR COMO DISPONÍVEL
            self._available = True
            self.being_provisioned = False
            
            print(f"[SERVICE_STEP] ✅ Serviço {self.id} DISPONÍVEL no servidor {self.server.id}")

            # Atualizar caminhos
            app = self.application
            users = app.users
            for user in users:
                user.set_communication_path(app)