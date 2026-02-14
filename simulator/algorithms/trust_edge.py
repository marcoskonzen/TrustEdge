# Importing EdgeSimPy components
from xml.parsers.expat import model
from edge_sim_py import *

# Importing native Python modules/packages
import json
import os
from datetime import datetime
import time

# Importing helper functions
from simulator.helper_functions import *

# Importing EdgeSimPy extensions
from simulator.extensions import *

"""TRUST EDGE ALGORITHM V3 - WITH PROACTIVE MIGRATION AND WAITING QUEUE"""

# ============================================================================
# GLOBAL PROVISIONING AND MIGRATION TRACKING SYSTEM
# ============================================================================

_provisioning_and_migration_metrics = {
    # ═══════════════════════════════════════════════════════════
    # PROVISIONAMENTOS
    # ═══════════════════════════════════════════════════════════
    "total_provisionings": 0,
    "provisionings_finished": 0,
    "provisionings_interrupted": 0,
    "provisioning_interruption_reasons": {
        "user_stopped_accessing": 0,
        "target_server_failed": 0,
    },
    
    # ═══════════════════════════════════════════════════════════
    # MIGRAÇÕES
    # ═══════════════════════════════════════════════════════════
    "total_migrations": 0,
    "migrations_finished": 0,
    "migrations_interrupted": 0,
    "migration_interruption_reasons": {
        "origin_server_failed": 0,
        "target_server_failed": 0,
        "user_stopped_accessing": 0,
    },
    
    # ═══════════════════════════════════════════════════════════
    # MIGRAÇÕES POR MOTIVO ORIGINAL
    # ═══════════════════════════════════════════════════════════
    "migrations_by_original_reason": {
        "delay_violation": 0,
        "low_reliability": 0,
        "predicted_failure": 0,
        "server_failed_unpredicted": 0,  # ← Cold migrations VERDADEIRAS
    },
    
    # ✅ NOVO: Detalhamento de Cold Migrations
    "cold_migration_analysis": {
        "total": 0,
        "instant_recovery": 0,          # Finalizou em 0 steps (camadas já estavam)
        "fast_recovery": 0,             # Finalizou em 1-5 steps
        "slow_recovery": 0,             # Finalizou em 6+ steps
        "failed_recovery": 0,           # Interrompida antes de finalizar
        
        "recovery_times": [],           # Lista de tempos (para calcular média)
        
        "by_downtime": {
            "zero_downtime": 0,         # Recuperação instantânea (0 steps)
            "low_downtime": 0,          # 1-5 steps de indisponibilidade
            "medium_downtime": 0,       # 6-15 steps
            "high_downtime": 0,         # 16+ steps
        }
    },
    
    # ═══════════════════════════════════════════════════════════
    # TEMPOS DE MIGRAÇÃO
    # ═══════════════════════════════════════════════════════════
    "migration_times": {
        "all_migrations": [],
        "by_reason": {
            "delay_violation": [],
            "low_reliability": [],
            "predicted_failure": [],
            "server_failed_unpredicted": [],
        }
    },
    
    # ═══════════════════════════════════════════════════════════
    # DOWNTIME DETALHADO (NOVA ESTRUTURA)
    # ═══════════════════════════════════════════════════════════
    "downtime_breakdown": {
        # Downtime causado por MIGRAÇÕES
        "migrations": {
            "total": 0,
            "waiting_in_global_queue": 0,      # Fila de espera global
            "waiting_in_download_queue": 0,    # Fila de download do servidor
            "downloading_layers_cold": 0,      # Download enquanto indisponível
            "cutover": 0,                      # Downtime durante cutover
            "delay_before_trigger": 0,         # ✅ NOVO: Delays acumulados antes de migrar
        },
        
        # Downtime causado por PROVISIONAMENTOS
        "provisionings": {
            "total": 0,
            "waiting_in_global_queue": 0,
            "waiting_in_download_queue": 0,
            "downloading_layers": 0,
        },
        
        # Downtime causado por FALHAS NÃO PREVISTAS
        "server_failures": {
            "total": 0,
            "orphaned_services": 0,            # ✅ NOVO: Serviço ficou órfão até reprovisionar
        },
    },
}

# SISTEMA DE RASTREAMENTO DE QUALIDADE DE PREVISÃO
# Janela dinâmica baseada no horizonte de predição
# Se prevemos falha em 100 steps, damos 150 steps para validar (margem de 50%)
_prediction_quality_metrics = {
    "proactive_migrations": [],  # [{..., "validation_window": 90}, ...]
    "true_positives": 0,
    "false_positives": 0,
    "false_negatives": 0,
}

_raw_latencies = []
_failed_target_attempts = {}  # {service_id: {server_id: step_when_failed}}

def reset_failed_target_attempts():
    """Limpa histórico de tentativas falhadas."""
    global _failed_target_attempts
    _failed_target_attempts = {}


def register_failed_migration_attempt(service_id, server_id, current_step):
    """Registra que uma tentativa de migração para um servidor falhou."""
    global _failed_target_attempts
    
    if service_id not in _failed_target_attempts:
        _failed_target_attempts[service_id] = {}
    
    _failed_target_attempts[service_id][server_id] = current_step
    print(f"[ANTI_RETRY] Bloqueando servidor {server_id} para serviço {service_id} temporariamente")

def clear_failed_attempts_for_service(service_id):
    """Limpa histórico de tentativas falhadas para um serviço específico."""
    global _failed_target_attempts
    
    if service_id in _failed_target_attempts:
        del _failed_target_attempts[service_id]

def _cleanup_all_log_guards(current_step):
    """Limpa todos os guards de logs a cada 100 steps."""
    global _server_log_guard, _t1_log_guard, _t3_log_guard
    
    if current_step % 100 != 0:
        return
    
    cutoff = current_step - 100
    
    # Remover logs de steps antigos (manter apenas últimos 100)
    _server_log_guard = {k for k in _server_log_guard if k[0] >= cutoff}
    _t1_log_guard = {k for k in _t1_log_guard if k[0] >= cutoff}
    _t3_log_guard = {k for k in _t3_log_guard if k[0] >= cutoff}
    
    # ✅ TAMBÉM LIMPAR guard de predict_failures
    from simulator.helper_functions import _cleanup_predict_failures_log_guard
    _cleanup_predict_failures_log_guard(current_step)
    
    print(f"[CLEANUP] Guards de logs limpos (mantendo últimos 100 steps)")

def initialize_provisioning_and_migration_tracking():
    """Inicializa o sistema unificado de rastreamento."""
    global _provisioning_and_migration_metrics
    _provisioning_and_migration_metrics = {
        # Provisionamentos (origin = None)
        "total_provisionings": 0,
        "provisionings_finished": 0,
        "provisionings_interrupted": 0,
        
        # Migrações (origin != None)
        "total_migrations": 0,
        "migrations_finished": 0,
        "migrations_interrupted": 0,
        
        # ✅ NOVO: Migrações por motivo ORIGINAL (antes de virar server_failed)
        "migrations_by_original_reason": {
            "delay_violation": 0,
            "low_reliability": 0,
            "predicted_failure": 0,
            "server_failed_unpredicted": 0,  # Cold migrations verdadeiras
        },
        
        # ✅ NOVO: Tempos de migração
        "migration_times": {
            "all_migrations": [],  # Lista com todos os tempos
            "by_reason": {
                "delay_violation": [],
                "low_reliability": [],
                "predicted_failure": [],
                "server_failed_unpredicted": [],
            }
        },
        
        # ✅ NOVO: Downtime efetivo causado por migrações
        "migration_downtime": {
            "total_steps": 0,
            "by_reason": {
                "delay_violation": 0,
                "low_reliability": 0,
                "predicted_failure": 0,
                "server_failed_unpredicted": 0,
            }
        },
        
        # Detalhes para auditoria
        "by_step": {},
    }
    print("[LOG] Sistema unificado de rastreamento inicializado")


def classify_migration_reason(original_server, reason):
    """
    Classifica a migração e retorna:
    - normalized_reason
    - original_reason
    - is_cold_migration
    - is_recovery_after_prevention
    """
    normalized_reason = reason
    if not normalized_reason or normalized_reason == "unknown":
        if original_server and not original_server.available:
            normalized_reason = "server_failed"
        else:
            normalized_reason = "unknown_forced"

    original_reason = normalized_reason
    is_cold_migration = False
    is_recovery_after_prevention = False

    if normalized_reason == "server_failed":
        if not original_server:
            original_reason = "initial_provisioning"
        else:
            had_preventive_attempt = any(
                item["server_id"] == original_server.id
                for item in _prediction_quality_metrics["proactive_migrations"]
                if not item.get("validated", False)
            )

            if not had_preventive_attempt:
                is_cold_migration = True
                original_reason = "server_failed_unpredicted"
            else:
                is_recovery_after_prevention = True
                preventive_migration = next(
                    (item for item in _prediction_quality_metrics["proactive_migrations"]
                     if item["server_id"] == original_server.id and not item.get("validated", False)),
                    None
                )
                original_reason = preventive_migration["reason"] if preventive_migration else "low_reliability"

    return normalized_reason, original_reason, is_cold_migration, is_recovery_after_prevention


def collect_final_provisioning_and_migration_metrics():
    """
    Coleta métricas finais consolidando TODAS as fontes de downtime.
    """
    global _provisioning_and_migration_metrics
    
    print(f"\n{'='*70}")
    print(f"COLETANDO MÉTRICAS FINAIS DE PROVISIONAMENTO E MIGRAÇÃO")
    print(f"{'='*70}\n")
    
    # Resetar contadores
    _provisioning_and_migration_metrics["total_provisionings"] = 0
    _provisioning_and_migration_metrics["provisionings_finished"] = 0
    _provisioning_and_migration_metrics["provisionings_interrupted"] = 0
    
    _provisioning_and_migration_metrics["provisioning_interruption_reasons"] = {
        "user_stopped_accessing": 0,
        "target_server_failed": 0,
    }
    
    _provisioning_and_migration_metrics["total_migrations"] = 0
    _provisioning_and_migration_metrics["migrations_finished"] = 0
    _provisioning_and_migration_metrics["migrations_interrupted"] = 0
    
    _provisioning_and_migration_metrics["migration_interruption_reasons"] = {
        "origin_server_failed": 0,
        "target_server_failed": 0,
        "user_stopped_accessing": 0,
    }
    
    _provisioning_and_migration_metrics["migrations_by_original_reason"] = {
        "delay_violation": 0,
        "low_reliability": 0,
        "predicted_failure": 0,
        "server_failed_unpredicted": 0,
    }
    
    _provisioning_and_migration_metrics["migration_times"]["all_migrations"] = []
    _provisioning_and_migration_metrics["migration_times"]["by_reason"] = {
        "delay_violation": [],
        "low_reliability": [],
        "predicted_failure": [],
        "server_failed_unpredicted": [],
    }
    
    # ✅ NOVO: Resetar breakdown de downtime
    _provisioning_and_migration_metrics["downtime_breakdown"] = {
        "migrations": {
            "total": 0,
            "waiting_in_global_queue": 0,
            "waiting_in_download_queue": 0,
            "downloading_layers_cold": 0,
            "cutover": 0,
            "delay_before_trigger": 0,
        },
        "provisionings": {
            "total": 0,
            "waiting_in_global_queue": 0,
            "waiting_in_download_queue": 0,
            "downloading_layers": 0,
        },
        "server_failures": {
            "total": 0,
            "orphaned_services": 0,
        },
    }
    
    # ═══════════════════════════════════════════════════════════
    # CONSOLIDAR DOWNTIME DO REGISTRO GLOBAL (user_perceived_downtime)
    # ═══════════════════════════════════════════════════════════
    
    from simulator.helper_functions import get_simulation_metrics
    global_metrics = get_simulation_metrics()
    downtime_records = global_metrics.downtime_reasons
    
    print(f"[COLLECT_METRICS] Total de registros de downtime: {sum(downtime_records.values())}")
    
    for cause, count in downtime_records.items():
        # Parsear causa para extrair categoria
        if cause.startswith("migration_"):
            # Exemplo: "migration_low_reliability_downloading_layers_cold"
            parts = cause.split("_", 2)  # ['migration', 'low', 'reliability_downloading_layers_cold']
            
            if len(parts) >= 3:
                # Extrair motivo original
                original_reason_candidate = parts[1]  # 'low'
                
                # Mapear para chaves válidas
                if "delay" in cause:
                    original_reason = "delay_violation"
                elif "low" in cause and "reliability" in cause:
                    original_reason = "low_reliability"
                elif "predicted" in cause and "failure" in cause:
                    original_reason = "predicted_failure"
                elif "server" in cause and "failed" in cause:
                    original_reason = "server_failed_unpredicted"
                else:
                    original_reason = "unknown"
                
                # Classificar subcategoria
                if "waiting_in_global_queue" in cause:
                    _provisioning_and_migration_metrics["downtime_breakdown"]["migrations"]["waiting_in_global_queue"] += count
                elif "waiting_in_download_queue" in cause:
                    _provisioning_and_migration_metrics["downtime_breakdown"]["migrations"]["waiting_in_download_queue"] += count
                elif "downloading_layers_cold" in cause:
                    _provisioning_and_migration_metrics["downtime_breakdown"]["migrations"]["downloading_layers_cold"] += count
                elif "cutover" in cause:
                    _provisioning_and_migration_metrics["downtime_breakdown"]["migrations"]["cutover"] += count
                
                _provisioning_and_migration_metrics["downtime_breakdown"]["migrations"]["total"] += count
        
        elif cause.startswith("provisioning_"):
            if "waiting_in_global_queue" in cause:
                _provisioning_and_migration_metrics["downtime_breakdown"]["provisionings"]["waiting_in_global_queue"] += count
            elif "waiting_in_download_queue" in cause:
                _provisioning_and_migration_metrics["downtime_breakdown"]["provisionings"]["waiting_in_download_queue"] += count
            elif "downloading_layers" in cause:
                _provisioning_and_migration_metrics["downtime_breakdown"]["provisionings"]["downloading_layers"] += count
            
            _provisioning_and_migration_metrics["downtime_breakdown"]["provisionings"]["total"] += count
        
        elif cause.startswith("server_failure_"):
            _provisioning_and_migration_metrics["downtime_breakdown"]["server_failures"]["orphaned_services"] += count
            _provisioning_and_migration_metrics["downtime_breakdown"]["server_failures"]["total"] += count
    
    # ═══════════════════════════════════════════════════════════
    # ✅ NOVO: Resetar análise de cold migrations
    # ═══════════════════════════════════════════════════════════
    _provisioning_and_migration_metrics["cold_migration_analysis"] = {
        "total": 0,
        "instant_recovery": 0,
        "fast_recovery": 0,
        "slow_recovery": 0,
        "failed_recovery": 0,
        "recovery_times": [],
        "by_downtime": {
            "zero_downtime": 0,
            "low_downtime": 0,
            "medium_downtime": 0,
            "high_downtime": 0,
        }
    }
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        for idx, migration in enumerate(service._Service__migrations):
            origin = migration.get("origin")
            status = migration.get("status", "unknown")
            original_reason = migration.get("original_migration_reason")
            interruption_reason = migration.get("interruption_reason")
            
            # Classificar: Provisionamento vs Migração
            is_provisioning = (origin is None)
            
            if is_provisioning:
                # PROVISIONAMENTO
                _provisioning_and_migration_metrics["total_provisionings"] += 1
                
                if status == "finished":
                    _provisioning_and_migration_metrics["provisionings_finished"] += 1
                elif status == "interrupted":
                    _provisioning_and_migration_metrics["provisionings_interrupted"] += 1
                    
                    # ✅ RASTREAR MOTIVO DA INTERRUPÇÃO
                    if interruption_reason in _provisioning_and_migration_metrics["provisioning_interruption_reasons"]:
                        _provisioning_and_migration_metrics["provisioning_interruption_reasons"][interruption_reason] += 1
                
            else:
                # MIGRAÇÃO
                _provisioning_and_migration_metrics["total_migrations"] += 1

                if status == "finished":
                    _provisioning_and_migration_metrics["migrations_finished"] += 1
                elif status == "interrupted":
                    _provisioning_and_migration_metrics["migrations_interrupted"] += 1

                    # ✅ RASTREAR MOTIVO DA INTERRUPÇÃO
                    if interruption_reason in _provisioning_and_migration_metrics["migration_interruption_reasons"]:
                        _provisioning_and_migration_metrics["migration_interruption_reasons"][interruption_reason] += 1

                # ✅ CONTABILIZAR POR RAZÃO ORIGINAL (UMA VEZ)
                if original_reason in _provisioning_and_migration_metrics["migrations_by_original_reason"]:
                    _provisioning_and_migration_metrics["migrations_by_original_reason"][original_reason] += 1

                # ✅ CALCULAR TEMPO DE MIGRAÇÃO
                if migration.get("end") and migration.get("start"):
                    duration = migration["end"] - migration["start"]
                    _provisioning_and_migration_metrics["migration_times"]["all_migrations"].append(duration)

                    if original_reason in _provisioning_and_migration_metrics["migration_times"]["by_reason"]:
                        _provisioning_and_migration_metrics["migration_times"]["by_reason"][original_reason].append(duration)
                
                # ═════════════════════════════════════════════════════════
                # ✅ NOVO: ANÁLISE DETALHADA DE COLD MIGRATIONS
                # ═════════════════════════════════════════════════════════
                if original_reason == "server_failed_unpredicted":
                    cold_analysis = _provisioning_and_migration_metrics["cold_migration_analysis"]
                    cold_analysis["total"] += 1

                    recovery_time = None
                    if migration.get("end") is not None and migration.get("start") is not None:
                        recovery_time = migration["end"] - migration["start"]
                        cold_analysis["recovery_times"].append(recovery_time)

                    if status == "interrupted":
                        cold_analysis["failed_recovery"] += 1
                    elif status == "finished":
                        if recovery_time == 0:
                            cold_analysis["instant_recovery"] += 1
                        elif recovery_time is not None and recovery_time <= 5:
                            cold_analysis["fast_recovery"] += 1
                        else:
                            cold_analysis["slow_recovery"] += 1
                    else:
                        # ✅ evita buracos nos buckets
                        cold_analysis["failed_recovery"] += 1

                    downtime_steps = migration.get("downtime_steps", 0)
                    if downtime_steps == 0:
                        cold_analysis["by_downtime"]["zero_downtime"] += 1
                    elif downtime_steps <= 5:
                        cold_analysis["by_downtime"]["low_downtime"] += 1
                    elif downtime_steps <= 15:
                        cold_analysis["by_downtime"]["medium_downtime"] += 1
                    else:
                        cold_analysis["by_downtime"]["high_downtime"] += 1
    
    print(f"✓ Métricas coletadas com sucesso\n")

def audit_migration_classification():
    """
    Audita TODAS as migrações para detectar classificações incorretas.
    Executa ao final da simulação.
    """
    print(f"\n{'='*70}")
    print(f"AUDITORIA DE CLASSIFICAÇÃO DE MIGRAÇÕES")
    print(f"{'='*70}\n")
    
    total_migrations = 0
    by_original_reason = {}
    by_migration_reason = {}
    missing_original_reason = []
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        for idx, migration in enumerate(service._Service__migrations):
            origin = migration.get("origin")
            
            # Pular provisionamentos
            if origin is None:
                continue
            
            total_migrations += 1
            
            migration_reason = migration.get("migration_reason", "unknown")
            original_reason = migration.get("original_migration_reason")
            
            # Contar por migration_reason
            if migration_reason not in by_migration_reason:
                by_migration_reason[migration_reason] = 0
            by_migration_reason[migration_reason] += 1
            
            # Contar por original_reason
            if original_reason:
                if original_reason not in by_original_reason:
                    by_original_reason[original_reason] = 0
                by_original_reason[original_reason] += 1
            else:
                missing_original_reason.append({
                    "service_id": service.id,
                    "migration_index": idx,
                    "migration_reason": migration_reason,
                    "origin_id": origin.id,
                })
    
    print(f"Total de migrações auditadas: {total_migrations}")
    
    print(f"\nPor migration_reason:")
    for reason, count in sorted(by_migration_reason.items(), key=lambda x: -x[1]):
        pct = (count / total_migrations * 100) if total_migrations > 0 else 0
        print(f"  {reason}: {count} ({pct:.1f}%)")
    
    print(f"\nPor original_migration_reason:")
    for reason, count in sorted(by_original_reason.items(), key=lambda x: -x[1]):
        pct = (count / total_migrations * 100) if total_migrations > 0 else 0
        print(f"  {reason}: {count} ({pct:.1f}%)")
    
    if missing_original_reason:
        print(f"\n⚠️ {len(missing_original_reason)} migrações SEM original_migration_reason:")
        for item in missing_original_reason[:5]:
            print(f"  Service {item['service_id']}, Migration {item['migration_index']}: "
                  f"migration_reason='{item['migration_reason']}', origin={item['origin_id']}")
        if len(missing_original_reason) > 5:
            print(f"  ... e mais {len(missing_original_reason) - 5} casos")
    
    # ✅ VALIDAÇÃO: Total deve bater
    sum_by_original = sum(by_original_reason.values())
    if sum_by_original != total_migrations:
        print(f"\n⚠️⚠️⚠️ INCONSISTÊNCIA CRÍTICA:")
        print(f"   Total de migrações: {total_migrations}")
        print(f"   Soma por original_reason: {sum_by_original}")
        print(f"   Diferença (missing): {total_migrations - sum_by_original}")
    else:
        print(f"\n✅ Classificação CONSISTENTE (total = soma por motivo)")
    
    print(f"\n{'='*70}\n")

def print_final_provisioning_and_migration_summary():
    """Imprime resumo COMPLETO com breakdown detalhado de downtime."""
    metrics = _provisioning_and_migration_metrics
    
    print(f"\n{'='*70}")
    print(f"RESUMO CONSOLIDADO DE PROVISIONAMENTO E MIGRAÇÃO")
    print(f"{'='*70}\n")
    
    # ═══════════════════════════════════════════════════════════
    # PROVISIONAMENTOS
    # ═══════════════════════════════════════════════════════════
    print(f"PROVISIONAMENTOS (Inicial - origin=None):")
    print(f"  Total de provisionamentos iniciados: {metrics['total_provisionings']}")
    
    if metrics['total_provisionings'] > 0:
        finished_pct = (metrics['provisionings_finished'] / metrics['total_provisionings']) * 100
        interrupted_pct = (metrics['provisionings_interrupted'] / metrics['total_provisionings']) * 100
        
        print(f"  └─ Finalizados com sucesso: {metrics['provisionings_finished']} ({finished_pct:.1f}%)")
        print(f"  └─ Interrompidos: {metrics['provisionings_interrupted']} ({interrupted_pct:.1f}%)")
        
        # ✅ NOVO: Breakdown de interrupções
        if metrics['provisionings_interrupted'] > 0:
            print(f"\n  ⚠️ Motivos das Interrupções:")
            for reason, count in metrics['provisioning_interruption_reasons'].items():
                if count > 0:
                    reason_pct = (count / metrics['provisionings_interrupted']) * 100
                    reason_name = {
                        "user_stopped_accessing": "Usuário parou de acessar",
                        "target_server_failed": "Servidor de destino falhou",
                    }.get(reason, reason)
                    print(f"    └─ {reason_name}: {count} ({reason_pct:.1f}%)")
    
    print()
    
    # ═══════════════════════════════════════════════════════════
    # MIGRAÇÕES
    # ═══════════════════════════════════════════════════════════
    print(f"MIGRAÇÕES (origin != None):")
    print(f"  Total de migrações iniciadas: {metrics['total_migrations']}")
    
    if metrics['total_migrations'] > 0:
        finished_pct = (metrics['migrations_finished'] / metrics['total_migrations']) * 100
        interrupted_pct = (metrics['migrations_interrupted'] / metrics['total_migrations']) * 100
        
        print(f"  └─ Finalizadas com sucesso: {metrics['migrations_finished']} ({finished_pct:.1f}%)")
        print(f"  └─ Interrompidas: {metrics['migrations_interrupted']} ({interrupted_pct:.1f}%)")
        
        # ✅ NOVO: Breakdown de interrupções
        if metrics['migrations_interrupted'] > 0:
            print(f"\n  ⚠️ Motivos das Interrupções:")
            for reason, count in metrics['migration_interruption_reasons'].items():
                if count > 0:
                    reason_pct = (count / metrics['migrations_interrupted']) * 100
                    reason_name = {
                        "origin_server_failed": "Servidor de origem falhou",
                        "target_server_failed": "Servidor de destino falhou",
                        "user_stopped_accessing": "Usuário parou de acessar",
                    }.get(reason, reason)
                    print(f"    └─ {reason_name}: {count} ({reason_pct:.1f}%)")
        
        # ✅ Migrações por motivo ORIGINAL
        print(f"\n  ✅ Migrações por MOTIVO ORIGINAL:")

    reason_order = [
        ("delay_violation", "Violação de SLA"),
        ("low_reliability", "Predição de Falha (Low Reliability)"),
        ("predicted_failure", "Predição de Falha (Immediate)"),
        ("server_failed_unpredicted", "❄️ Falha NÃO Prevista (Cold Migration)")
    ]

    total_preventive_from_metrics = (
        metrics['migrations_by_original_reason'].get('low_reliability', 0) +
        metrics['migrations_by_original_reason'].get('predicted_failure', 0)
    )

    for reason_key, display_name in reason_order:
        count = metrics['migrations_by_original_reason'].get(reason_key, 0)
        reason_pct = (count / metrics['total_migrations']) * 100 if metrics['total_migrations'] > 0 else 0
        print(f"    └─ {display_name}: {count} ({reason_pct:.1f}%)")
    
    # ═══════════════════════════════════════════════════════════
    # ✅ NOVO: ANÁLISE DETALHADA DE COLD MIGRATIONS
    # ═══════════════════════════════════════════════════════════
    cold_analysis = metrics.get('cold_migration_analysis', {})
    total_cold = cold_analysis.get('total', 0)
    
    if total_cold > 0:
        print(f"\n  ❄️ ANÁLISE DETALHADA DE COLD MIGRATIONS (Falhas Não Previstas):")
        print(f"    └─ Total de cold migrations: {total_cold}")
        
        # Eficiência de recuperação
        print(f"\n    ⚡ Eficiência de Recuperação:")
        
        instant = cold_analysis.get('instant_recovery', 0)
        fast = cold_analysis.get('fast_recovery', 0)
        slow = cold_analysis.get('slow_recovery', 0)
        failed = cold_analysis.get('failed_recovery', 0)
        
        if instant > 0:
            instant_pct = (instant / total_cold) * 100
            print(f"      └─ Recuperação Instantânea (0 steps): {instant} ({instant_pct:.1f}%)")
            print(f"         💡 Camadas já estavam no servidor de destino")
        
        if fast > 0:
            fast_pct = (fast / total_cold) * 100
            print(f"      └─ Recuperação Rápida (1-5 steps): {fast} ({fast_pct:.1f}%)")
        
        if slow > 0:
            slow_pct = (slow / total_cold) * 100
            print(f"      └─ Recuperação Lenta (6+ steps): {slow} ({slow_pct:.1f}%)")
        
        if failed > 0:
            failed_pct = (failed / total_cold) * 100
            print(f"      └─ Recuperação Falhou (interrompida): {failed} ({failed_pct:.1f}%)")
        
        # Tempo médio de recuperação
        recovery_times = cold_analysis.get('recovery_times', [])
        if recovery_times:
            avg_recovery = sum(recovery_times) / len(recovery_times)
            min_recovery = min(recovery_times)
            max_recovery = max(recovery_times)
            
            print(f"\n    ⏱️ Tempos de Recuperação:")
            print(f"      └─ Média: {avg_recovery:.2f} steps")
            print(f"      └─ Mínimo: {min_recovery} steps | Máximo: {max_recovery} steps")
        
        # Downtime causado
        print(f"\n    ⏸️ Downtime Causado por Cold Migrations:")
        
        by_downtime = cold_analysis.get('by_downtime', {})
        
        zero_dt = by_downtime.get('zero_downtime', 0)
        low_dt = by_downtime.get('low_downtime', 0)
        medium_dt = by_downtime.get('medium_downtime', 0)
        high_dt = by_downtime.get('high_downtime', 0)
        
        if zero_dt > 0:
            zero_pct = (zero_dt / total_cold) * 100
            print(f"      └─ Sem downtime (0 steps): {zero_dt} ({zero_pct:.1f}%)")
        
        if low_dt > 0:
            low_pct = (low_dt / total_cold) * 100
            print(f"      └─ Downtime baixo (1-5 steps): {low_dt} ({low_pct:.1f}%)")
        
        if medium_dt > 0:
            medium_pct = (medium_dt / total_cold) * 100
            print(f"      └─ Downtime médio (6-15 steps): {medium_dt} ({medium_pct:.1f}%)")
        
        if high_dt > 0:
            high_pct = (high_dt / total_cold) * 100
            print(f"      └─ Downtime alto (16+ steps): {high_dt} ({high_pct:.1f}%)")
        
        # ✅ VALIDAÇÃO FINAL
        successful_recoveries = instant + fast + slow
        if successful_recoveries == total_cold - failed:
            print(f"\n    ✅ Validação: {successful_recoveries}/{total_cold} cold migrations bem-sucedidas")
        else:
            print(f"\n    ⚠️ Inconsistência detectada na classificação de cold migrations")
    
    # ═══════════════════════════════════════════════════════════
    # DOWNTIME BREAKDOWN COMPLETO
    # ═══════════════════════════════════════════════════════════
    print(f"\n  📊 BREAKDOWN COMPLETO DO DOWNTIME:")
    
    breakdown = metrics['downtime_breakdown']
    
    migration_downtime = breakdown['migrations']['total']
    provisioning_downtime = breakdown['provisionings']['total']
    failure_downtime = breakdown['server_failures']['total']
    
    # Coletar downtime total da simulação
    total_perceived = None
    try:
        from simulator.helper_functions import collect_all_sla_violations
        consolidated = collect_all_sla_violations()
        total_perceived = consolidated.get("total_perceived_downtime", 0)
    except:
        pass
    
    print(f"\n    └─ Downtime por FALHA NÃO PREVISTA:")
    print(f"       └─ Serviços órfãos (aguardando reprovisionar): {breakdown['server_failures']['orphaned_services']} steps")
    print(f"       └─ Total: {failure_downtime} steps")
    
    print(f"\n    └─ Downtime durante MIGRAÇÕES: {migration_downtime} steps")
    if migration_downtime > 0:
        print(f"       └─ Fila de espera global: {breakdown['migrations']['waiting_in_global_queue']} steps")
        print(f"       └─ Fila de download do servidor: {breakdown['migrations']['waiting_in_download_queue']} steps")
        print(f"       └─ Download de camadas (Cold): {breakdown['migrations']['downloading_layers_cold']} steps")
        print(f"       └─ Cutover (Live Migration): {breakdown['migrations']['cutover']} steps")
    
    print(f"\n    └─ Downtime durante PROVISIONAMENTOS: {provisioning_downtime} steps")
    if provisioning_downtime > 0:
        print(f"       └─ Fila de espera global: {breakdown['provisionings']['waiting_in_global_queue']} steps")
        print(f"       └─ Fila de download do servidor: {breakdown['provisionings']['waiting_in_download_queue']} steps")
        print(f"       └─ Download de camadas: {breakdown['provisionings']['downloading_layers']} steps")
    
    tracked_total = migration_downtime + provisioning_downtime + failure_downtime
    
    print(f"\n    └─ Total rastreado: {tracked_total} steps")
    
    if total_perceived:
        print(f"    └─ Total percebido (simulação): {total_perceived} steps")
        
        if tracked_total != total_perceived:
            diff = abs(total_perceived - tracked_total)
            diff_pct = (diff / total_perceived * 100) if total_perceived > 0 else 0
            
            if tracked_total < total_perceived:
                print(f"    └─ ⚠️ Diferença não rastreada: {diff} steps ({diff_pct:.1f}%)")
            else:
                print(f"    └─ ⚠️ Diferença (sobrecontagem): {diff} steps ({diff_pct:.1f}%)")
        else:
            print(f"    └─ ✅ Total rastreado BATE com total percebido!")
    
    print(f"\n{'='*70}\n")
    
    # ═══════════════════════════════════════════════════════════
    # QUALIDADE DE PREVISÃO
    # ═══════════════════════════════════════════════════════════
    print(f"{'='*70}")
    print(f"ANÁLISE DE QUALIDADE DA PREVISÃO (TrustEdge)")
    print(f"{'='*70}")
    
    tp = _prediction_quality_metrics["true_positives"]
    fp = _prediction_quality_metrics["false_positives"]
    fn = _prediction_quality_metrics["false_negatives"]
    total_proactive = len(_prediction_quality_metrics["proactive_migrations"])
    
    # ✅ VALIDAÇÃO: Total preventivo deve bater com proactive_migrations
    total_proactive = len(_prediction_quality_metrics["proactive_migrations"])
    print(f"Migrações preventivas rastreadas: {total_proactive}")

    if total_preventive_from_metrics != total_proactive:
        print(f"⚠️ INCONSISTÊNCIA DETECTADA:")
        print(f"   Migrações preventivas (by_reason): {total_preventive_from_metrics}")
        print(f"   Migrações preventivas (prediction_quality): {total_proactive}")
        print(f"   Diferença: {abs(total_preventive_from_metrics - total_proactive)}")
    
    validated = tp + fp
    pending = total_proactive - validated
    
    if pending > 0:
        print(f"  └─ ⏳ Pendentes de validação: {pending}")
    
    print(f"Reações a falhas não previstas (Cold Migration): {fn}")
    
    # ✅ VALIDAR contra migrations_by_original_reason
    cold_migrations_from_metrics = metrics['migrations_by_original_reason'].get('server_failed_unpredicted', 0)
    
    if fn != cold_migrations_from_metrics:
        print(f"\n⚠️ INCONSISTÊNCIA DETECTADA:")
        print(f"   False Negatives rastreados: {fn}")
        print(f"   Cold Migrations contadas: {cold_migrations_from_metrics}")
        print(f"   Diferença: {abs(fn - cold_migrations_from_metrics)}")
    
    if validated > 0:
        precision = (tp / validated) * 100
        print(f"\n📊 MÉTRICAS DE QUALIDADE:")
        print(f"  Precision: {precision:.2f}% ({tp}/{validated} validados)")
    
    total_failures = tp + fn
    if total_failures > 0:
        recall = (tp / total_failures) * 100
        print(f"  Recall: {recall:.2f}% ({tp}/{total_failures} falhas)")
        
        if validated > 0:
            f1 = 2 * (precision * recall) / (precision + recall)
            print(f"  F1-Score: {f1:.2f}%")
    
    print(f"{'='*70}\n")

def get_provisioning_and_migration_metrics():
    """Retorna as métricas para análise externa."""
    return _provisioning_and_migration_metrics.copy()


def audit_migration_times():
    """Audita tempos de migração para detectar anomalias (DEBUG)."""
    anomalies = []
    
    print(f"\n{'='*70}")
    print(f"AUDITORIA DE TEMPOS DE MIGRAÇÃO (DEBUG)")
    print(f"{'='*70}\n")
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        for i, mig in enumerate(service._Service__migrations):
            if mig["end"] is None:
                continue  # Pular migrações ativas
            
            duration = mig['end'] - mig['start']
            
            # Calcular tempo rastreado
            tracked_time = (
                mig.get('waiting_time', 0) + 
                mig.get('pulling_layers_time', 0) + 
                mig.get('migrating_service_state_time', 0) +
                mig.get('interrupted_time', 0)
            )
            
            discrepancy = duration - tracked_time
            
            # Verificar anomalia (tolerância de 1 step)
            if discrepancy > 1:
                origin = mig.get("origin")
                target = mig.get("target")
                status = mig.get("status", "unknown")
                
                print(f"⚠️ ANOMALIA - Serviço {service.id} | Migração {i+1}")
                print(f"   Status: {status}")
                print(f"   Origin: {origin.id if origin else 'None'} → Target: {target.id if target else 'None'}")
                print(f"   Duração: {duration} steps | Rastreado: {tracked_time} steps")
                print(f"   Missing: {discrepancy} steps\n")
                
                anomalies.append({
                    'service': service.id,
                    'migration': i + 1,
                    'duration': duration,
                    'tracked': tracked_time,
                    'missing': discrepancy,
                    'status': status
                })
    
    if anomalies:
        print(f"Total de anomalias encontradas: {len(anomalies)}")
    else:
        print(f"✓ Nenhuma anomalia detectada")
    
    print(f"{'='*70}\n")


def audit_server_failed_migrations():
    """Audita TODAS as migrações marcadas como server_failed."""
    
    print(f"\n{'='*70}")
    print(f"AUDITORIA DE MIGRAÇÕES 'server_failed'")
    print(f"{'='*70}\n")
    
    cold_count = 0
    hot_count = 0
    cold_details = []
    hot_details = []
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations'):
            continue
        
        for i, mig in enumerate(service._Service__migrations):
            if mig.get("migration_reason") != "server_failed":
                continue
            
            origin = mig.get("origin")
            target = mig.get("target")
            is_cold = mig.get("is_cold_migration", False)
            start = mig.get("start")
            end = mig.get("end", "N/A")
            
            if is_cold:
                cold_count += 1
                cold_details.append({
                    "service_id": service.id,
                    "migration_index": i + 1,
                    "origin_id": origin.id if origin else None,
                    "target_id": target.id if target else None,
                    "start": start,
                    "end": end
                })
            else:
                hot_count += 1
                hot_details.append({
                    "service_id": service.id,
                    "migration_index": i + 1,
                    "origin_id": origin.id if origin else None,
                    "target_id": target.id if target else None,
                    "start": start,
                    "end": end
                })
    
    # Mostrar primeiras 5 COLD migrations
    print(f"❄️ COLD MIGRATIONS (Falhas NÃO previstas):")
    for i, detail in enumerate(cold_details[:5], 1):
        print(f"  {i}. Service {detail['service_id']} | Migration {detail['migration_index']}")
        print(f"     Origin: {detail['origin_id']} → Target: {detail['target_id']}")
        print(f"     Steps: {detail['start']} - {detail['end']}")
    
    if cold_count > 5:
        print(f"  ... e mais {cold_count - 5} COLD migrations")
    
    print(f"\n♻️ HOT MIGRATIONS (Reprovisioning após previsão):")
    for i, detail in enumerate(hot_details[:5], 1):
        print(f"  {i}. Service {detail['service_id']} | Migration {detail['migration_index']}")
        print(f"     Origin: {detail['origin_id']} → Target: {detail['target_id']}")
        print(f"     Steps: {detail['start']} - {detail['end']}")
    
    if hot_count > 5:
        print(f"  ... e mais {hot_count - 5} HOT migrations")
    
    print(f"\n📊 RESUMO:")
    print(f"  ❄️ COLD Migrations (FN verdadeiros): {cold_count}")
    print(f"  ♻️ HOT Migrations (Reprovisioning): {hot_count}")
    print(f"  📦 Total server_failed: {cold_count + hot_count}")
    
    # Validar contra métricas
    fn = _prediction_quality_metrics["false_negatives"]
    if cold_count != fn:
        print(f"\n⚠️ ALERTA: Discrepância detectada!")
        print(f"   COLD migrations contadas: {cold_count}")
        print(f"   False Negatives rastreados: {fn}")
        print(f"   Diferença: {abs(cold_count - fn)}")
    else:
        print(f"\n✅ VALIDADO: COLD migrations ({cold_count}) = False Negatives ({fn})")
    
    print(f"{'='*70}\n")


def audit_server_resources(current_step):
    """Audita consistência dos recursos dos servidores."""
    
    if current_step % 50 != 0:
        return
    
    print(f"\n[AUDITORIA] === VERIFICAÇÃO DE RECURSOS - STEP {current_step} ===")
    
    anomalies_found = False
    
    # ✅ NOVO: Detectar serviços duplicados
    service_locations = {}  # {service_id: [server_ids]}
    
    for server in EdgeServer.all():
        # Verificar recursos negativos
        cpu_available = server.cpu - server.cpu_demand
        memory_available = server.memory - server.memory_demand
        
        if cpu_available < 0 or memory_available < 0:
            anomalies_found = True
            print(f"[AUDITORIA] ⚠️ SERVIDOR {server.id} COM RECURSOS NEGATIVOS!")
            print(f"            CPU disponível: {cpu_available}/{server.cpu}")
            print(f"            Memory disponível: {memory_available}/{server.memory}")
        
        # Verificar inconsistências de relacionamento
        for service in server.services:
            # Rastrear localização do serviço
            if service.id not in service_locations:
                service_locations[service.id] = []
            service_locations[service.id].append(server.id)
            
            if service.server != server:
                anomalies_found = True
                print(f"[AUDITORIA] ⚠️ INCONSISTÊNCIA: Serviço {service.id} na lista do servidor {server.id}")
                print(f"            mas service.server = {service.server.id if service.server else None}")
    
    # ✅ Verificar duplicatas
    for service_id, server_ids in service_locations.items():
        if len(server_ids) > 1:
            anomalies_found = True
            print(f"[AUDITORIA] ⚠️ DUPLICATA: Serviço {service_id} está em MÚLTIPLOS servidores!")
            print(f"            Servidores: {server_ids}")
    
    if not anomalies_found:
        print(f"[AUDITORIA] ✅ Nenhuma anomalia detectada")
    
    print(f"[AUDITORIA] === FIM VERIFICAÇÃO ===\n")

# ============================================================================
# GLOBAL WAITING QUEUE FOR UNPROVISIONED APPLICATIONS
# ============================================================================

_waiting_queue = []

def get_waiting_queue():
    """Retorna a fila de espera global."""
    return _waiting_queue


def add_to_waiting_queue(user, application, service, priority_score=0, reason="server_failed"):
    """Adiciona uma aplicação à fila de espera."""
    # Verificar se a aplicação já está na fila
    for item in _waiting_queue:
        if item["application"].id == application.id:
            print(f"[LOG] Aplicação {application.id} já está na fila de espera.")
            return

    user.delays[str(application.id)] = float('inf')

    service._waiting_reason = reason
    service._waiting_queue_start_step = user.model.schedule.steps + 1  # ✅ NOVA FLAG

    waiting_item = {
        "user": user,
        "application": application,
        "service": service,
        "priority_score": priority_score,
        "reason": reason,
        "queued_at_step": user.model.schedule.steps,
        "delay": user.delays[str(application.id)],
        "delay_sla": user.delay_slas[str(application.id)],
        "delay_cost": get_application_delay_cost(application),
        "intensity_score": get_application_access_intensity_score(application),
        "demand_resource": get_normalized_demand(application.services[0]),
        "delay_urgency": get_delay_urgency(application, user)
    }

    _waiting_queue.append(waiting_item)
    print(f"[LOG] Aplicação {application.id} adicionada à fila de espera (Prioridade: {priority_score:.4f}), Razão: {reason}")

def remove_from_waiting_queue(application_id):
    """Remove uma aplicação da fila de espera."""
    global _waiting_queue
    _waiting_queue = [item for item in _waiting_queue if item["application"].id != application_id]


def diagnose_layer_downloads(current_step):
    """Diagnostica de onde as camadas estão sendo baixadas e limitações."""
    
    print("=" * 70)
    print(f"[DEBUG_DOWNLOADS] === ANÁLISE DE DOWNLOADS DE CAMADAS - STEP {current_step} ===")
    print("=" * 70)

    registries = ContainerRegistry.all()
    
    if not registries:
        print(f"[DEBUG_DOWNLOADS] ⚠️ Nenhum Container Registry encontrado!")
        return
    
    print(f"[DEBUG_DOWNLOADS] ✓ Container Registries encontrados: {len(registries)}")
    
    for registry in registries:
        if not hasattr(registry, 'server') or registry.server is None:
            continue
        
        total_layers = sum(1 for layer in ContainerLayer.all() 
                          if hasattr(layer, 'server') and layer.server and layer.server.id == registry.server.id)
        
        print(f"[DEBUG_DOWNLOADS]   Registry {registry.id}:")
        print(f"                 - Camadas armazenadas: {total_layers}")
    
    # Verificar servidores com downloads ativos
    servers_with_activity = []
    total_active_downloads = 0
    
    # ✅ NOVO: Rastrear camadas em download ativo
    layers_being_downloaded = set()
    
    for server in EdgeServer.all():
        # Coletar camadas em download ativo
        for flow in server.download_queue:
            if hasattr(flow, 'metadata') and flow.metadata.get('type') == 'layer':
                layer = flow.metadata.get('object')
                if layer and hasattr(layer, 'digest'):
                    layers_being_downloaded.add(layer.digest)
        
        if len(server.download_queue) > 0 or len(server.services) > 0:
            has_inconsistency = False
            
            if len(server.download_queue) > 0 and server.cpu_demand == 0 and server.memory_demand == 0:
                has_inconsistency = True
            
            if len(server.services) > 0 and server.cpu_demand == 0 and server.memory_demand == 0:
                has_inconsistency = True
            
            if len(server.download_queue) > 0:
                servers_with_activity.append(server)
                total_active_downloads += len(server.download_queue)
            
            if len(server.download_queue) > 0 or len(server.services) > 0:
                status_icon = "⚠️" if has_inconsistency else " "
                print(f"[DEBUG_DOWNLOADS] {status_icon} Servidor {server.id}:")
                print(f"               - Serviços alocados: {len(server.services)} (IDs: {[s.id for s in server.services]})")
                print(f"               - Downloads ativos: {len(server.download_queue)}")
                print(f"               - Waiting queue: {len(server.waiting_queue)}")
                print(f"               - Recursos: CPU={server.cpu_demand}/{server.cpu}, MEM={server.memory_demand}/{server.memory}")
                
                if has_inconsistency:
                    print(f"               ❌ SERVIDOR FALHOU!")
    
    print(f"[DEBUG_DOWNLOADS] Total de downloads ativos: {total_active_downloads}")
    print(f"[DEBUG_DOWNLOADS] Servidores com downloads: {len(servers_with_activity)}")
    print(f"[DEBUG_DOWNLOADS] === FIM DO DEBUG DE DOWNLOADS ===\n")
    
    # ✅ ESTATÍSTICAS DETALHADAS
    all_layers = ContainerLayer.all()
    
    # Categorizar camadas
    layers_in_registry = set()  # Camadas do registry (templates)
    layers_in_servers = set()   # Camadas já baixadas nos servidores
    layers_orphaned = []         # Camadas órfãs reais (lixo)
    
    # 1. Identificar camadas do registry
    for registry in registries:
        if hasattr(registry, 'server') and registry.server:
            for layer in registry.server.container_layers:
                if hasattr(layer, 'digest'):
                    layers_in_registry.add(layer.digest)
    
    # 2. Identificar camadas nos servidores
    for layer in all_layers:
        if hasattr(layer, 'server') and layer.server:
            if hasattr(layer, 'digest'):
                layers_in_servers.add(layer.digest)
    
    # 3. Identificar camadas órfãs (excluindo as que estão em download)
    for layer in all_layers:
        if not hasattr(layer, 'server') or layer.server is None:
            layer_digest = layer.digest if hasattr(layer, 'digest') else None
            
            # Excluir se está no registry (template válido)
            if layer_digest in layers_in_registry:
                continue
            
            # ✅ NOVO: Excluir se está sendo baixada ativamente
            if layer_digest in layers_being_downloaded:
                continue
            
            # É uma camada órfã real
            layers_orphaned.append(layer)
    
    print(f"[DEBUG_DOWNLOADS] Estatísticas gerais:")
    print(f"               - Total de camadas no sistema: {len(all_layers)}")
    print(f"               - Camadas em registries (templates): {len(layers_in_registry)}")
    print(f"               - Camadas em servidores: {len(layers_in_servers)}")
    print(f"               - Camadas em download ativo: {len(layers_being_downloaded)}")
    print(f"               - Camadas órfãs (lixo): {len(layers_orphaned)}")
    
    if layers_orphaned:
        print(f"\n[DEBUG_DOWNLOADS] ⚠️ Camadas órfãs detectadas:")
        for i, layer in enumerate(layers_orphaned[:5], 1):
            layer_digest = layer.digest[:8] if hasattr(layer, 'digest') else 'N/A'
            layer_size = layer.size if hasattr(layer, 'size') else 0
            print(f"               {i}. Layer {layer_digest} (ID: {layer.id}, Size: {layer_size})")
        
        if len(layers_orphaned) > 5:
            print(f"               ... e mais {len(layers_orphaned) - 5} camadas órfãs")
    
    print(f"[DEBUG_DOWNLOADS] === FIM DO DEBUG DE DOWNLOADS ===\n")


def collect_server_resource_snapshot(current_step):
    """Retorna uso e disponibilidade de recursos dos servidores no step informado."""
    
    print()
    print("=" * 70)
    print(f"[DEBUG_STATUS_SERVER] === SNAPSHOT SERVERS - STEP {current_step} ===")
    print("=" * 70)

    snapshot = []

    total_cpu = 0
    total_memory = 0
    total_cpu_demand = 0
    total_memory_demand = 0

    available_cpu_capacity = 0
    available_memory_capacity = 0
    available_cpu_demand = 0
    available_memory_demand = 0

    unavailable_cpu_capacity = 0
    unavailable_memory_capacity = 0

    def _pct(value, reference):
        return (value / reference * 100) if reference else 0.0

    for server in EdgeServer.all():
        cpu_available = server.cpu - server.cpu_demand
        mem_available = server.memory - server.memory_demand

        if server.status == "available":
            reliability = get_server_conditional_reliability_weibull(server, 1)
        else:
            reliability = 0.0

        entry = {
            "step": current_step,
            "server_id": server.id,
            "status": server.status,
            "available": server.available,
            "cpu_total": server.cpu,
            "cpu_demand": server.cpu_demand,
            "cpu_available": cpu_available,
            "memory_total": server.memory,
            "memory_demand": server.memory_demand,
            "memory_available": mem_available,
            "reliability": reliability,
        }
        snapshot.append(entry)

        print(
            f"[SERVER_SNAPSHOT] Server {server.id} | "
            f"Status={server.status} | Available={server.available} | "
            f"CPU {server.cpu_demand}/{server.cpu} (free={cpu_available}) | "
            f"MEM {server.memory_demand}/{server.memory} (free={mem_available}) | "
            f"Reliability={reliability:.2f}%"
        )

        # Totais globais
        total_cpu += server.cpu
        total_memory += server.memory
        total_cpu_demand += server.cpu_demand
        total_memory_demand += server.memory_demand

        if server.available:
            available_cpu_capacity += server.cpu
            available_memory_capacity += server.memory
            available_cpu_demand += server.cpu_demand
            available_memory_demand += server.memory_demand
        else:
            unavailable_cpu_capacity += server.cpu
            unavailable_memory_capacity += server.memory

    unavailable_cpu_capacity = max(0, total_cpu - available_cpu_capacity)
    unavailable_memory_capacity = max(0, total_memory - available_memory_capacity)

    summary = {
        "step": current_step,
        "totals": {
            "cpu": total_cpu,
            "memory": total_memory,
        },
        "available_resources": {
            "cpu": available_cpu_capacity,
            "cpu_pct_of_total": _pct(available_cpu_capacity, total_cpu),
            "memory": available_memory_capacity,
            "memory_pct_of_total": _pct(available_memory_capacity, total_memory),
        },
        "unavailable_resources": {
            "cpu": unavailable_cpu_capacity,
            "cpu_pct_of_total": _pct(unavailable_cpu_capacity, total_cpu),
            "memory": unavailable_memory_capacity,
            "memory_pct_of_total": _pct(unavailable_memory_capacity, total_memory),
        },
        "consumption": {
            "cpu": total_cpu_demand,
            "cpu_pct_of_total": _pct(total_cpu_demand, total_cpu),
            "cpu_pct_of_available": _pct(available_cpu_demand, available_cpu_capacity),
            "memory": total_memory_demand,
            "memory_pct_of_total": _pct(total_memory_demand, total_memory),
            "memory_pct_of_available": _pct(available_memory_demand, available_memory_capacity),
        },
    }

    print()
    print(f"[SERVER_SNAPSHOT] --- RESUMO INFRA ---")
    print(
        f"[SERVER_SNAPSHOT] Recursos totais -> CPU={total_cpu} | MEM={total_memory}"
    )
    print(
        f"[SERVER_SNAPSHOT] Recursos disponíveis -> "
        f"CPU={available_cpu_capacity} ({summary['available_resources']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={available_memory_capacity} ({summary['available_resources']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Recursos indisponíveis -> "
        f"CPU={unavailable_cpu_capacity} ({summary['unavailable_resources']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={unavailable_memory_capacity} ({summary['unavailable_resources']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Consumo total -> "
        f"CPU={total_cpu_demand} ({summary['consumption']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={total_memory_demand} ({summary['consumption']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Consumo dos recursos disponíveis -> "
        f"CPU={available_cpu_demand} ({summary['consumption']['cpu_pct_of_available']:.2f}% dos disponíveis) | "
        f"MEM={available_memory_demand} ({summary['consumption']['memory_pct_of_available']:.2f}% dos disponíveis)"
    )

    return {"snapshot": snapshot, "summary": summary}


# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def trust_edge_v3(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge V3."""
    import time
    
    # Início da medição de tempo do algoritmo (CPU time)
    step_start_time = time.process_time()
    
    # Extrair parâmetros de sensibilidade
    window_size = parameters.get("window_size", 30)
    reliability_threshold = parameters.get("reliability_threshold", 60.0)
    delay_threshold = parameters.get("delay_threshold", 1.0)
    
    _te_enable_p2p = os.environ.get('TRUSTEDGE_ENABLE_P2P', '1') == '1'
    _te_enable_live = os.environ.get('TRUSTEDGE_ENABLE_LIVE_MIGRATION', '1') == '1'
    _te_enable_prediction = os.environ.get('TRUSTEDGE_ENABLE_FAILURE_PREDICTION', '1') == '1'

    model = Topology.first().model
    current_step = parameters.get("current_step")
    model._trust_edge_current_step = current_step
    model._te_enable_p2p = _te_enable_p2p
    model._te_enable_live = _te_enable_live
    model._te_enable_prediction = _te_enable_prediction
    model._trust_edge_window_size = window_size
    model._trust_edge_reliability_threshold = reliability_threshold
    model._trust_edge_delay_threshold = delay_threshold

    # Configurar módulos M3/M4
    from simulator.extensions.service_extensions import configure_migration_strategy
    configure_migration_strategy(
        enable_live_migration=_te_enable_live,
        enable_state_transfer=_te_enable_live,
    )

    try:
        from simulator.extensions.edge_server_extensions import configure_layer_download
        configure_layer_download(
            enable_p2p=_te_enable_p2p,
            enable_registry=True,
        )
    except ImportError:
        # configure_layer_download não existe — P2P é controlado
        # diretamente pelo edge_server_extensions.custom_collect_method
        if _te_enable_p2p:
            print(f"[TRUSTEDGE] ⚠️ configure_layer_download não encontrado — P2P controlado via env var")
        pass

    print(f"\n[TRUSTEDGE] Module Configuration:")
    print(f"  M1 (Orchestration Policy):   ALWAYS ON ✅")
    print(f"  M2 (Failure Prediction):     {'ON ✅' if _te_enable_prediction else 'OFF ❌'}")
    print(f"  M3 (P2P Layer Download):     {'ON ✅' if _te_enable_p2p else 'OFF ❌'}")
    print(f"  M4 (Live Migration):         {'ON ✅' if _te_enable_live else 'OFF ❌'}\n")

    # Inicializar acumulador de tempo no modelo (apenas no step 1)
    if not hasattr(model, '_trust_edge_total_execution_time'):
        model._trust_edge_total_execution_time = 0.0

    # Inicializar tracking no primeiro step
    if current_step == 1:

        global _raw_latencies
        _raw_latencies = []
        
        from simulator.extensions.edge_server_extensions import configure_layer_download_strategy, _rebuild_layer_index
        from simulator.extensions.service_extensions import configure_migration_strategy
        
        configure_layer_download_strategy(enable_p2p=_te_enable_p2p, enable_registry=True)
        configure_migration_strategy(enable_live_migration=_te_enable_live, enable_state_transfer=_te_enable_live)

        _rebuild_layer_index(current_step)
        initialize_provisioning_and_migration_tracking()
        init_failure_reliability_tracking()
        reset_weibull_estimation_cache()
        reset_failed_target_attempts()
        
        print(f"\n{'='*70}\n[TRUST_EDGE_V3] Configuração: W={window_size}, R={reliability_threshold}%, D={delay_threshold}x\n{'='*70}\n")

        # Validar histórico pré-carregado
        print(f"\n{'='*70}")
        print(f"[HISTÓRICO] Validando dados pré-carregados:")
        print(f"{'='*70}")
        
        # ✅ NOVO: Inicializar _perceived_downtime para todos os usuários
        for user in User.all():
            if not hasattr(user, '_perceived_downtime'):
                user._perceived_downtime = {}
        
        for server in EdgeServer.all():
            if server.model_name == "Jetson TX2":  # Registry
                continue
            
            history_size = len(server.failure_model.failure_history)
            print(f"Server {server.id}: {history_size} falhas no histórico")
            
            if history_size > 0:
                # Mostrar primeira e última falha
                first = server.failure_model.failure_history[0]
                last = server.failure_model.failure_history[-1]
                print(f"  ├─ Primeira falha: step {first['failure_starts_at']}")
                print(f"  └─ Última falha: step {last['becomes_available_at']}")
                
                # Testar estimação Weibull
                params = estimate_weibull_parameters_from_history(server, window_size=window_size)
                print(f"  └─ Weibull: shape={params['tbf_shape']:.3f}, "
                      f"scale={params['tbf_scale']:.1f}, quality={params['estimation_quality']}")
        
        print(f"{'='*70}\n")

        # ✅ NOVO: Testar previsão de falhas
        print(f"\n{'='*70}")
        print(f"[TESTE_PREVISÃO] Testando predict_next_n_failures():")
        print(f"{'='*70}")
        
        # Testar em 3 servidores aleatórios
        test_servers = [s for s in EdgeServer.all() if s.model_name != "Jetson TX2"][:3]
        
        for server in test_servers:
            print(f"\n[TESTE_PREVISÃO] Server {server.id}:")
            
            # Testar com horizonte 150
            predictions = predict_next_n_failures(server, n_failures=3, max_horizon=150)
            
            print(f"[TESTE_PREVISÃO] Resultado: {len(predictions)} previsões dentro de 150 steps")
            
            if len(predictions) == 0:
                # Testar com horizonte maior para diagnóstico
                predictions_long = predict_next_n_failures(server, n_failures=3, max_horizon=500)
                print(f"[TESTE_PREVISÃO] Com horizonte 500: {len(predictions_long)} previsões")
                
                if len(predictions_long) > 0:
                    print(f"[TESTE_PREVISÃO] ⚠️ Primeira falha em {predictions_long[0]['horizon']} steps (longe demais!)")
        
        print(f"{'='*70}\n")

    # Registrar confiabilidade quando uma falha começa neste step
    record_server_failure_reliability(current_step)
    
    print()
    print()
    print(f"\n[TRUST_EDGE_V3] ===  ⬇️ ⬇️ ⬇️  INÍCIO DO STEP {current_step}  ⬇️ ⬇️ ⬇️  ===")

    # ✅ Limpar guards periodicamente
    _cleanup_all_log_guards(current_step)

    if current_step %10 ==0:
        from simulator.helper_functions import _cleanup_provisioning_time_cache
        _cleanup_provisioning_time_cache(current_step)
    
    # 1. Diagnóstico (reduzir frequência)
    if current_step == 1 or current_step % 50 == 0:
        diagnose_layer_downloads(current_step)

    # Isso garante que a estimativa leve em conta falhas recentes IMEDIATAMENTE.
    for server in EdgeServer.all():
        # Verifica se o servidor acabou de se recuperar ou falhar
        # Se o tamanho do histórico mudou desde a última checagem, invalida cache
        if not hasattr(server, '_last_history_len'):
            server._last_history_len = 0
            
        current_history_len = len(server.failure_model.failure_history)
        
        if current_history_len != server._last_history_len:
            # Histórico mudou! (Nova falha registrada pelo edge_server_extensions)
            # Limpar cache do Weibull para este servidor
            from simulator.helper_functions import _weibull_estimation_cache
            if server.id in _weibull_estimation_cache:
                del _weibull_estimation_cache[server.id]
                print(f"[WEIBULL_UPDATE] 🔄 Cache invalidado para Server {server.id} (Nova falha registrada)")
            
            server._last_history_len = current_history_len

    # 2. Coleta e resumo dos recursos e demandas dos servidores
    collect_server_resource_snapshot(current_step)

    # 4. Verificar e desprovisionar serviços inativos e inconsistentes
    check_and_deprovision_inactive_services(current_step)
    
    # 5. Atualizar delays
    update_application_delays(current_step)

    # 6. Processar fila de espera
    process_waiting_queue(current_step)

    # 7. Monitoramento das migrações
    monitor_and_migrate_services(parameters)

    # 8. Provisionamento de novas requisições
    provision_new_requests(current_step)

    # 9. Atuaizar o downtime percebido
    update_user_perceived_downtime_for_current_step(current_step)

    validate_tracking_consistency(current_step)

    # Validar previsões passadas
    validate_predictions(current_step)

    # 10. Coleta de métricas da simulação
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()

    step_duration = time.process_time() - step_start_time
    model._trust_edge_total_execution_time += step_duration

    # 11. Relatório de provisionamentos e migrações
    if parameters.get("time_steps") == current_step:
        print(f"\n[TRUST_EDGE_V3] Simulação finalizada - coletando métricas finais...\n", flush=True)
        
        diagnose_weibull_estimations(current_step)

        audit_migration_classification()

        diagnose_downtime_sla_violations()
        
        # Coletar métricas auditando todas as operações
        collect_final_provisioning_and_migration_metrics()
        
        # Imprimir resumo consolidado
        print_final_provisioning_and_migration_summary()

        # Auditoria de migrações com falhas de servidor
        audit_server_failed_migrations()

        # Relatório de confiabilidade no momento das falhas
        print_failure_reliability_summary()

        # Imprimir relatório de casos não classificados
        from simulator.helper_functions import print_unclassified_downtime_report
        print_unclassified_downtime_report()

        # Salvar métricas em JSON
        save_final_metrics_to_json(run_id=parameters.get("run_id"))
        
        # Auditoria de tempos (opcional - para debug)
        # audit_migration_times()


# ============================================================================
# WAITING QUEUE PROCESSING
# ============================================================================

def process_waiting_queue(current_step):
    """Processa a fila de espera tentando provisionar aplicações em servidores disponíveis."""
    
    if not _waiting_queue:
        print(f"[DEBUG_WAITING_QUEUE] Fila de espera vazia")
        return
    
    print(f"\n[DEBUG_WAITING_QUEUE] === PROCESSANDO FILA DE ESPERA - STEP {current_step} ===")
    print(f"[DEBUG_WAITING_QUEUE] {len(_waiting_queue)} aplicações na fila")
    
    provisioned_items = []
    
    for waiting_item in _waiting_queue:
        user = waiting_item["user"]
        app = waiting_item["application"]
        service = waiting_item["service"]
        queued_step = waiting_item["queued_at_step"]
        
        # Verificar se o usuário ainda está acessando
        if not is_user_accessing_application(user, app, current_step):
            print(f"[LOG] Usuário {user.id} não está mais acessando aplicação {app.id} - removendo da fila")
            provisioned_items.append(waiting_item)
            continue
        
        remaining_time = get_remaining_access_time(user, app, current_step)
            
        print(f"\n[DEBUG_WAITING_QUEUE] Tentando provisionar aplicação {app.id} da fila:")
        print(f"      Usuário: {user.id}")
        print(f"      Tempo na fila: {current_step - queued_step} steps")
        print(f"      Tempo restante: {remaining_time} steps")
        
        # Tentar provisionar
        if try_provision_service(user, app, service, reason=waiting_item.get("reason")):
            provisioned_items.append(waiting_item)
            if hasattr(service, "_waiting_reason"):
                del service._waiting_reason
            if hasattr(service, "_waiting_queue_start_step"):
                del service._waiting_queue_start_step
        else:
            print(f"[DEBUG_WAITING_QUEUE] Aplicação {app.id} ainda não pode ser provisionada")
    
    # Remover itens processados da fila
    for item in provisioned_items:
        _waiting_queue.remove(item)
    
    print(f"[DEBUG_WAITING_QUEUE] {len(provisioned_items)} aplicações processadas")
    print(f"[DEBUG_WAITING_QUEUE] {len(_waiting_queue)} aplicações restantes na fila")
    print(f"[DEBUG_WAITING_QUEUE] === FIM PROCESSAMENTO FILA DE ESPERA ===\n")

def get_delay_urgency(application, user):
    """Calcula urgência baseada na proximidade da violação de SLA."""
    user_app = user
    app = application
    current_delay = user_app.delays[str(app.id)] if user_app.delays[str(app.id)] is not None else 0
    delay_sla = user_app.delay_slas[str(app.id)]
    return delay_sla - current_delay  # Quanto menor, mais urgente

# ============================================================================
# SERVICE MONITORING AND MIGRATION
# ============================================================================

def monitor_and_migrate_services(parameters: dict = {}):
    """Monitora servidores e migra serviços quando necessário."""
    current_step = parameters.get("current_step")
    
    reliability_threshold = parameters.get("reliability_threshold", 95.0)
    delay_threshold = parameters.get("delay_threshold", 1.0)
    
    print()
    print("=" * 70)
    print(f"[DEBUG_MONITORING] === MONITORAMENTO E MIGRAÇÃO - STEP {current_step} ===")
    print("=" * 70)
    
    # 2. Verificar migrações em andamento
    check_ongoing_migrations(current_step)
    
    # 3. Identificar novos serviços para migração
    services_to_migrate = identify_services_for_migration(current_step, reliability_threshold, delay_threshold)

    # 4. Processar fila de migração
    process_migration_queue(services_to_migrate, current_step)
    
    print(f"[DEBUG_MONITORING] === FIM MONITORAMENTO E MIGRAÇÃO ===\n")


def check_ongoing_migrations(current_step):
    """
    Verifica e processa TODAS as migrações:
    1. Migrações finalizadas (finished)
    2. Migrações interrompidas (interrupted)
    3. Migrações ativas (em andamento) - Gerencia Live Migration
    """
    print(f"\n[DEBUG_MONITORING] === VERIFICANDO MIGRAÇÕES - STEP {current_step} ===")
    
    migrations_finished = 0
    migrations_interrupted = 0
    migrations_active = 0
    services_to_requeue = []

    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
            
        migration = service._Service__migrations[-1]
        origin = migration.get("origin")
        target = migration.get("target")
        
        # ✅ OBTER STATUS NO INÍCIO (antes de todos os casos)
        status = migration.get("status", "unknown")
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 1: MIGRAÇÕES MARCADAS PARA CANCELAMENTO (edge_server_step)
        # ═══════════════════════════════════════════════════════════════
        if migration.get("_pending_cancellation") and migration.get("end") is None:
            cancellation_reason = migration.get("_cancellation_reason", "server_failed")
            
            print(f"[DEBUG_MONITORING] 🔴 Migração MARCADA para cancelamento - Serviço {service.id}")
            print(f"                   Razão: {cancellation_reason}")
            
            # Cancelar usando função existente
            if cancel_service_migration(service, reason=cancellation_reason):
                print(f"[DEBUG_MONITORING] ✓ Migração cancelada")
                
                # Limpar flags
                del migration["_pending_cancellation"]
                if "_cancellation_reason" in migration:
                    del migration["_cancellation_reason"]
                
                migrations_interrupted += 1
                
                # Verificar se precisa reprocessar
                app = service.application
                user = app.users[0]
                
                if is_user_accessing_application(user, app, current_step):
                    services_to_requeue.append({
                        "service": service,
                        "app": app,
                        "user": user,
                        "reason": cancellation_reason
                    })
            
            continue  # Pular demais verificações
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 2: MIGRAÇÕES FINALIZADAS NO STEP ATUAL
        # ═══════════════════════════════════════════════════════════════
        if migration["end"] == current_step:
            
            if status == "finished":
                migrations_finished += 1
                print(f"[DEBUG_MONITORING] ✅ Migração FINALIZADA - Serviço {service.id}")
                
                # Validar consistência (Garantir que está no target)
                if service.server != target:
                    print(f"[DEBUG_MONITORING] ⚠️ Corrigindo: service.server={service.server.id if service.server else None}, esperado={target.id}")
                    service.server = target
                    if service not in target.services:
                        target.services.append(service)
                
                # Limpar origem definitivamente
                if origin and service in origin.services:
                    origin.services.remove(service)
                    
            elif status == "interrupted":
                migrations_interrupted += 1
                cause = migration.get("interruption_reason", "unknown")
                print(f"[DEBUG_MONITORING] ⚠️ Migração INTERROMPIDA - Serviço {service.id}")
                print(f"                   Causa: {cause}")
                
                # Verificar se precisa reprocessar
                app = service.application
                user = app.users[0]
                
                if is_user_accessing_application(user, app, current_step):
                    services_to_requeue.append({
                        "service": service,
                        "app": app,
                        "user": user,
                        "reason": cause
                    })
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 3: MIGRAÇÕES AINDA ATIVAS (Gerenciamento de Live Migration)
        # ═══════════════════════════════════════════════════════════════
        elif migration["end"] is None:
            migrations_active += 1
            
            # ✅ RASTREAR DOWNTIME (para migrações E provisionamentos)
            if origin is None:
                # Provisionamento inicial
                track_provisioning_downtime(service, migration, current_step)
            else:
                # Migração
                track_migration_downtime(service, migration, current_step)
            
            # ───────────────────────────────────────────────────────────
            # ✅ ADICIONAR AQUI: Verificar falha do DESTINO
            # ───────────────────────────────────────────────────────────
            if target and not target.available:
                print(f"[DEBUG_MONITORING] ⚠️ Servidor de destino {target.id} FALHOU - Interrompendo migração")
                
                migration["status"] = "interrupted"
                migration["interruption_reason"] = "target_server_failed"  # ✅ ADICIONAR
                migration["end"] = current_step
                
                migrations_interrupted += 1
                
                # Verificar se precisa reprocessar
                app = service.application
                user = app.users[0]
                
                if is_user_accessing_application(user, app, current_step):
                    services_to_requeue.append({
                        "service": service,
                        "app": app,
                        "user": user,
                        "reason": "target_server_failed"
                    })
                
                continue  # Pular demais verificações desta migração
            
            # ───────────────────────────────────────────────────────────
            # A. Verificar falha da Origem durante Live Migration
            # ───────────────────────────────────────────────────────────
            if service.server == origin:
                # ✅ ADICIONAR AQUI: Verificar falha da ORIGEM
                if origin and not origin.available:
                    print(f"[DEBUG_MONITORING] ⚠️ Origem {origin.id} FALHOU durante Live Migration - Forçando transição para target")
                    
                    # Forçar mudança para target (mesmo sem downloads completos)
                    if origin and service in origin.services:
                        origin.services.remove(service)
                    
                    service.server = target
                    if service not in target.services:
                        target.services.append(service)
                    
                    # Serviço fica indisponível até downloads terminarem
                    service._available = False
                    
                    print(f"[DEBUG_MONITORING] Serviço {service.id} movido para {target.id} (aguardando camadas)")
            
            # ───────────────────────────────────────────────────────────
            # B. Cutover (Live Migration - Transferência de Estado)
            # ───────────────────────────────────────────────────────────
            if migration["status"] == "migrating_service_state" and service.server == origin:
                print(f"[DEBUG_MONITORING] ✂️ Cutover: Downloads concluídos. Movendo serviço {service.id} de {origin.id} para {target.id}")
                
                # Remover da origem
                if origin and service in origin.services:
                    origin.services.remove(service)
                
                # Mover para destino
                service.server = target
                if service not in target.services:
                    target.services.append(service)
                
                # ✅ CORREÇÃO: RASTREAR downtime durante cutover
                # Pequeno downtime simulado durante a transferência de estado
                service._available = False
                
                # ✅ ADICIONAR: Rastrear downtime do cutover
                if not service._available:
                    # Incrementar contador de cutover
                    if "downtime_steps" not in migration:
                        migration["downtime_steps"] = {"cutover": 0}
                    elif "cutover" not in migration["downtime_steps"]:
                        migration["downtime_steps"]["cutover"] = 0
                    
                    migration["downtime_steps"]["cutover"] += 1

    # ═══════════════════════════════════════════════════════════════
    # REPROCESSAR SERVIÇOS AFETADOS
    # ═══════════════════════════════════════════════════════════════
    if services_to_requeue:
        print(f"\n[DEBUG_MONITORING] Reprocessando {len(services_to_requeue)} serviços afetados:")
        
        for item in services_to_requeue:
            service = item["service"]
            app = item["app"]
            user = item["user"]
            reason = item["reason"]
            
            # Verificar se servidor ainda existe e está disponível
            if service.server and service.server.available:
                print(f"  - Serviço {service.id}: Servidor {service.server.id} OK - não reprocessar")
            else:
                print(f"  - Serviço {service.id}: Sem servidor válido - adicionando à fila (prioridade 999)")
                add_to_waiting_queue(user, app, service, priority_score=999.0)

    # Log resumo
    print(f"\n[DEBUG_MONITORING] Resumo:")
    if migrations_active > 0:
        print(f"  - {migrations_active} migrações ativas")
    if migrations_finished > 0:
        print(f"  - {migrations_finished} migrações finalizadas")
    if migrations_interrupted > 0:
        print(f"  - {migrations_interrupted} migrações interrompidas")
    if len(services_to_requeue) > 0:
        print(f"  - {len(services_to_requeue)} serviços reenfileirados")
    if migrations_active == 0 and migrations_finished == 0 and migrations_interrupted == 0:
        print(f"  - Nenhuma atividade de migração")
    
    print(f"[DEBUG_MONITORING] === FIM VERIFICAÇÃO MIGRAÇÕES ===\n")


def track_migration_downtime(service, migration, current_step):
    """
    Rastreia downtime efetivo causado pela migração.
    Chamado a cada step durante migração ativa.
    """
    # ✅ Inicializar rastreamento na primeira vez
    if "downtime_steps" not in migration:
        migration["downtime_steps"] = 0
        migration["downtime_causes"] = {
            "waiting_in_download_queue": 0,
            "downloading_layers_cold": 0,
            "cutover_unavailability": 0,
        }
    
    # ✅ Se serviço está INDISPONÍVEL neste step, rastrear causa
    if not service._available:
        migration["downtime_steps"] += 1
        
        status = migration.get("status", "unknown")
        origin = migration.get("origin")
        target = migration.get("target")
        
        # Determinar causa do downtime
        if status == "waiting":
            # Aguardando iniciar download
            migration["downtime_causes"]["waiting_in_download_queue"] += 1
            
        elif status == "pulling_layers":
            # Cold migration: baixando camadas enquanto indisponível
            if not origin or not origin.available:
                migration["downtime_causes"]["downloading_layers_cold"] += 1
            
        elif status == "migrating_service_state":
            # Cutover: transferindo estado
            migration["downtime_causes"]["cutover_unavailability"] += 1


def track_provisioning_downtime(service, migration, current_step):
    """
    Rastreia downtime durante PROVISIONAMENTO INICIAL.
    Similar ao track_migration_downtime mas para origin=None.
    """
    # ✅ Inicializar rastreamento
    if "downtime_steps" not in migration:
        migration["downtime_steps"] = 0
        migration["downtime_causes"] = {
            "waiting_in_download_queue": 0,
            "downloading_layers_cold": 0,
        }
    
    # Se serviço está INDISPONÍVEL durante provisionamento
    if not service._available:
        migration["downtime_steps"] += 1
        
        status = migration.get("status", "unknown")
        
        if status == "waiting":
            migration["downtime_causes"]["waiting_in_download_queue"] += 1
        elif status == "pulling_layers":
            migration["downtime_causes"]["downloading_layers_cold"] += 1

def identify_services_for_migration(current_step, reliability_threshold, delay_threshold):
    """Identifica serviços que precisam ser migrados."""
    services_to_migrate = []
    processed_services = set()
    
    # Configuração de Histerese Temporal (Cooldown)
    # Impede que um serviço migre novamente menos de 5 steps após chegar
    MIGRATION_COOLDOWN = 5

    for user in User.all():
        # ✅ PULAR usuários fazendo nova requisição (provisionamento em andamento)
        if is_making_request(user, current_step):
            continue

        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            server = service.server
            
            if service.id in processed_services:
                continue
            processed_services.add(service.id)
            
            # ═════════════════════════════════════════════════════════════
            # PROTEÇÕES E FILTROS
            # ═════════════════════════════════════════════════════════════

            # ✅ PROTEÇÃO 0: COOLDOWN (Evitar Ping-Pong)
            # Só aplica se o servidor atual estiver VIVO. Se falhou, ignora cooldown.
            if server and server.available:
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_mig = service._Service__migrations[-1]
                    # Se a última migração terminou há pouco tempo
                    if last_mig.get("end") is not None:
                        steps_since_migration = current_step - last_mig["end"]
                        if steps_since_migration < MIGRATION_COOLDOWN:
                            # print(f"[DEBUG] App {app.id} em COOLDOWN ({steps_since_migration}/{MIGRATION_COOLDOWN} steps) - pulando")
                            continue

            # ✅ PROTEÇÃO 1: Detectar provisionamento inicial ou migração ativa
            has_active_migration = False
            if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                last_migration = service._Service__migrations[-1]
                
                if last_migration["end"] is None:  # Processo em andamento
                    has_active_migration = True
                    
                    # Diferenciar: provisionamento inicial vs migração
                    if last_migration.get("origin") is None:
                        print(f"[DEBUG] App {app.id} em PROVISIONAMENTO INICIAL - pulando")
                    else:
                        print(f"[DEBUG] App {app.id} em MIGRAÇÃO ATIVA - pulando")
                    
                    continue  # ← Pular ambos os casos
            
            # ✅ PROTEÇÃO 2: Pular se está na fila de espera
            if is_application_in_waiting_queue(app.id):
                print(f"[DEBUG] App {app.id} na fila de espera - pulando")
                continue
            
            # ═════════════════════════════════════════════════════════════
            # AVALIAR CRITÉRIOS DE MIGRAÇÃO
            # ═════════════════════════════════════════════════════════════
            
            # ✅ CASO ESPECIAL: Servidor falhou (MÁXIMA PRIORIDADE)
            # Neste caso, delay = inf MAS NÃO tem migração ativa
            if server and not server.available:
                print(f"[DEBUG] App {app.id}: Servidor {server.id} FALHOU - MIGRAÇÃO URGENTE")
                services_to_migrate.append({
                    "service": service,
                    "application": app,
                    "user": user,
                    "current_server": server,
                    "reason": "server_failed",
                    "priority": 0,  # ← Prioridade 0 = MÁXIMA
                    "remaining_access_time": app_info["remaining_time"],
                    "criteria_data": {
                        "needs_migration": True,
                        "reason": "server_failed",
                        "priority": 0
                    }
                })
                continue  # ← Pular demais verificações
            
            # ✅ Servidor deve estar disponível para avaliar outros critérios
            if not server:
                print(f"[DEBUG] App {app.id} sem servidor - pulando avaliação")
                continue
            
            # ✅ Delay deve ser válido para avaliar violação
            current_delay = user.delays.get(str(app.id))
            
            if not has_active_migration:
                if current_delay is None or current_delay == float('inf'):
                    # Se chegou aqui com delay infinito, algo está errado
                    # (servidor disponível MAS delay infinito = inconsistência)
                    print(f"[DEBUG] App {app.id}: INCONSISTÊNCIA detectada!")
                    print(f"        Servidor: {server.id} (available={server.available})")
                    print(f"        Delay: {current_delay}")
                    continue
            
            # ✅ AVALIAÇÃO NORMAL: delay e confiabilidade
            migration_criteria = evaluate_migration_criteria(
                service=service,
                server=server,
                user=user,
                app=app,
                remaining_time=app_info["remaining_time"],
                reliability_threshold=reliability_threshold,
                delay_threshold=delay_threshold,
                current_step=current_step
            )
            
            if migration_criteria["needs_migration"]:
                services_to_migrate.append({
                    "service": service,
                    "application": app,
                    "user": user,
                    "current_server": server,
                    "reason": migration_criteria["reason"],
                    "priority": migration_criteria["priority"],
                    "remaining_access_time": app_info["remaining_time"],
                    "criteria_data": migration_criteria
                })
    
    return services_to_migrate

_prediction_cache_by_step = {}
_t1_log_guard = set()
_t3_log_guard = set()
_server_log_guard = set()

def evaluate_migration_criteria(
    server, 
    service, 
    current_step, 
    reliability_threshold,
    delay_threshold,
    user=None,              
    app=None,               
    remaining_time=None     
):
    """Avalia critérios para migração com THRESHOLD ADAPTATIVO e PREVISÃO MULTI-HORIZONTE."""
    
    # ✅ VALIDAÇÃO: Se user/app não foram passados, tentar obter do service
    if user is None or app is None:
        if not service.application or not service.application.users:
            # Sem contexto válido, retornar sem migração
            return {"needs_migration": False}
        
        app = service.application
        user = app.users[0]
    
    # ✅ VALIDAÇÃO: Calcular remaining_time se não foi passado
    if remaining_time is None:
        remaining_time = get_remaining_access_time(user, app, current_step)
    
    # -------------------------------------------------------------------------
    # Pré-cálculo: estimar tempo de migração (melhor candidato) uma única vez
    # -------------------------------------------------------------------------
    candidates = get_host_candidates(user, service)
    viable_candidates = [
        c for c in candidates
        if c["object"].id != server.id and c["object"].has_capacity_to_host(service)
    ]

    migration_time_needed = None
    if viable_candidates:
        viable_candidates.sort(key=lambda c: c["amount_of_uncached_layers"])
        best_candidate = viable_candidates[0]["object"]
        
        # ✅ CORREÇÃO: Extrair valor numérico do dicionário
        migration_time_result = estimate_migration_time_in_steps(best_candidate, service)
        migration_time_needed = migration_time_result.get('total_time_steps', float('inf'))

    # -------------------------------------------------------------------------
    # T1: Previsão de Falha (SEGURANÇA PRIMEIRO) - MULTI-HORIZONTE
    # -------------------------------------------------------------------------
    model = Topology.first().model
    prediction_enabled = getattr(model, '_te_enable_prediction', True)
    if prediction_enabled:
        try:
            prob_threshold = float(os.environ.get("TRUSTEDGE_PREDICTION_PROB_THRESHOLD", 50))
        except:
            prob_threshold = 50.0

        SAFETY_MARGIN = 5
        min_window = (migration_time_needed if migration_time_needed != float('inf') else 0) + SAFETY_MARGIN
        horizons_to_check = [
            ("immediate", 50),
            ("short", 150),
            ("medium", 300),
        ]

        best_prediction = None
        for label, horizon in horizons_to_check:
            predictions = _get_cached_predictions(server, horizon, current_step)
            if predictions:
                predictions = sorted(predictions, key=lambda p: (p["horizon"], -p.get("probability", 0)))
                best_prediction = predictions[0]
                if (current_step, server.id) not in _t1_log_guard:
                    print(f"[T1_MULTI] Server {server.id}: {len(predictions)} falhas em horizonte '{label}' ({horizon}s)")
                break
        log_key = (current_step, server.id)
        if log_key not in _server_log_guard:
            print("")
            _server_log_guard.add(log_key)

        if not best_prediction:
            if (current_step, server.id) not in _t1_log_guard:
                print(f"[T1_MULTI] Server {server.id}: Nenhuma falha prevista em 300 steps")
        _t1_log_guard.add((current_step, server.id))

        if best_prediction:
            time_until_failure = best_prediction["horizon"]
            probability = best_prediction.get("probability", 0)
            expected_downtime = best_prediction.get("expected_downtime", 0)

            # Janela mínima para evitar migração tardia
            min_window = (migration_time_needed or 0) + SAFETY_MARGIN
            impacts_current_session = time_until_failure <= remaining_time
            is_immediate_danger = time_until_failure <= max(30, min_window)

            if probability >= prob_threshold and (impacts_current_session or is_immediate_danger):
                print(f"[T1_URGENT] Falha em {time_until_failure}s (P={probability:.1f}%), "
                    f"migração leva {migration_time_needed}s → ACIONAR T1")
                return {
                    "needs_migration": True,
                    "reason": "predicted_failure",
                    "priority": 1,
                    "failure_horizon": time_until_failure,
                    "failure_probability": probability,
                    "expected_downtime": expected_downtime,
                    "migration_time_needed": migration_time_needed,
                }

        # -------------------------------------------------------------------------
        # T2: Baixa Confiabilidade (RISCO)
        # -------------------------------------------------------------------------
        try:
            env_lookahead = int(os.environ.get('TRUSTEDGE_LOOKAHEAD', 50))
        except:
            env_lookahead = 50

        SAFETY_MARGIN_STEPS = 30
        MINIMUM_LOOKAHEAD = 60

        base_check = max(remaining_time + SAFETY_MARGIN_STEPS, MINIMUM_LOOKAHEAD)
        check_horizon = max(base_check, env_lookahead)

        params = get_cached_weibull_parameters(server, current_step)
        mtbf = params.get('mtbf_estimated', 200)
        MAX_LOOKAHEAD = max(300, int(mtbf * 1.5))
        check_horizon = min(check_horizon, MAX_LOOKAHEAD)

        reliability_data = get_server_conditional_reliability_weibull_with_confidence(
            server, upcoming_instants=check_horizon
        )
        conditional_reliability = reliability_data['reliability']

        log_t3_allowed = (current_step, server.id) not in _t3_log_guard

        if log_t3_allowed:
            print(f"[T3_HORIZON] Server {server.id}: check_horizon={check_horizon}, max={MAX_LOOKAHEAD} (1.5x MTBF={mtbf:.0f})")

        # T1.5 - Degradação rápida
        if hasattr(server, '_reliability_history'):
            history = server._reliability_history
            if len(history) >= 5:
                recent = history[-5:]
                degradation_rate = (recent[0] - recent[-1]) / 10

                if degradation_rate > 5.0 and conditional_reliability < reliability_threshold:
                    print(f"[T1.5_RAPID_DEGRADATION] Server {server.id}: Degradação rápida (-{degradation_rate:.1f}%/step)")
                    return {
                        "needs_migration": True,
                        "reason": "low_reliability",
                        "priority": 2,
                        "reliability_value": conditional_reliability,
                        "degradation_rate": degradation_rate,
                        "migration_time_needed": migration_time_needed,
                        "conditional_reliability": conditional_reliability,
                    }
                else:
                    print(f"[T1.5_IGNORED] Degradação detectada mas R={conditional_reliability:.1f}% >= threshold={reliability_threshold:.1f}%")

        # Atualizar histórico
        if not hasattr(server, '_reliability_history'):
            server._reliability_history = []
        server._reliability_history.append(conditional_reliability)
        if len(server._reliability_history) > 10:
            server._reliability_history.pop(0)

        # Threshold efetivo (sensível ao tempo restante)
        HEALTH_THRESHOLD = reliability_threshold
        if remaining_time <= 50:
            HEALTH_THRESHOLD = min(95.0, HEALTH_THRESHOLD + 5.0)

        if log_t3_allowed:
            print(f"[T3_FIXED] Server {server.id}: MTBF={mtbf:.0f}, Threshold={HEALTH_THRESHOLD:.0f}%, R={conditional_reliability:.1f}%")

        if conditional_reliability < HEALTH_THRESHOLD:
            if log_t3_allowed:
                print(f"[LOG] ⚠️ Servidor {server.id} degradado (R={conditional_reliability:.1f}% < {HEALTH_THRESHOLD:.0f}%). Acionando T3.")
            _t3_log_guard.add((current_step, server.id))
            return {
                "needs_migration": True,
                "reason": "low_reliability",
                "priority": 2,
                "reliability_value": conditional_reliability,
                "threshold_used": HEALTH_THRESHOLD,
                "migration_time_needed": migration_time_needed,
                "conditional_reliability": conditional_reliability,
            }
        
        _t3_log_guard.add((current_step, server.id))
    else:
        # ─────────────────────────────────────────────────────────────
        # PREDIÇÃO DESABILITADA: Pular T1, T1.5, T2
        # Apenas calcular conditional_reliability para metadados (valor padrão)
        # ─────────────────────────────────────────────────────────────
        conditional_reliability = 100.0  # Assume confiabilidade perfeita sem predição
        print(f"[PREDICTION_OFF] Server {server.id}: Módulo M2 desabilitado — pulando T1/T1.5/T2")

    # -------------------------------------------------------------------------
    # T3: Violação de Delay (PERFORMANCE)
    # -------------------------------------------------------------------------
    current_delay = user.delays[str(app.id)] if user.delays[str(app.id)] is not None else 0
    delay_sla = user.delay_slas[str(app.id)]
    delay_limit = delay_sla * delay_threshold

    if current_delay > delay_limit:
        # Evita migrar se não há tempo para completar migração
        if migration_time_needed is None or remaining_time <= migration_time_needed:
            return {"needs_migration": False}

        print(f"[LOG] ⚠️ Delay violado (App {app.id}: {current_delay:.1f} > {delay_limit:.1f}). Acionando T2.")
        return {
            "needs_migration": True,
            "reason": "delay_violation",
            "priority": 3,
            "delay_violation_ratio": current_delay / delay_sla,
            "migration_time_needed": migration_time_needed,
            "conditional_reliability": conditional_reliability,
        }

    return {"needs_migration": False}

def is_application_in_waiting_queue(application_id):
    """Verifica se uma aplicação já está na fila de espera."""
    return any(item["application"].id == application_id for item in _waiting_queue)

def process_migration_queue(services_to_migrate, current_step):
    """Processa fila de serviços que precisam ser migrados."""
    if not services_to_migrate:
        print(f"[DEBUG_MONITORING] Nenhum serviço para migrar")
        return
    
    # ✅ NOVO: Limpar tentativas muito antigas (>100 steps atrás)
    global _failed_target_attempts
    CLEANUP_THRESHOLD = 100
    
    services_to_clean = []
    for service_id, attempts in list(_failed_target_attempts.items()):
        # Remover tentativas antigas de cada serviço
        cleaned_attempts = {
            server_id: step 
            for server_id, step in attempts.items() 
            if (current_step - step) <= CLEANUP_THRESHOLD
        }
        
        if cleaned_attempts:
            _failed_target_attempts[service_id] = cleaned_attempts
        else:
            # Serviço não tem mais tentativas recentes → Remover
            services_to_clean.append(service_id)
    
    for service_id in services_to_clean:
        del _failed_target_attempts[service_id]
    
    # Ordenar por prioridade e urgência
    services_to_migrate.sort(key=lambda s: (
        s["priority"],
        -s["criteria_data"].get("expected_downtime", 0),
        -s["criteria_data"].get("migration_time_needed", 0),
        -s["criteria_data"].get("delay_violation_ratio", 0),
        s["criteria_data"].get("conditional_reliability", 100)
    ))
    
    print(f"[DEBUG_MONITORING] Processando {len(services_to_migrate)} serviços para migração")
    
    for service_metadata in services_to_migrate:
        service = service_metadata["service"]
        app = service_metadata["application"]
        user = service_metadata["user"]
        current_server = service_metadata["current_server"]
        reason = service_metadata["reason"]
        criteria_data = service_metadata.get("criteria_data", {})
        
        print(f"\n[DEBUG_MONITORING] Migrando serviço {service.id} - Razão: {reason}")
        
        if (not current_server):
            print(f"[DEBUG_MONITORING] Servidor atual: NENHUM (Servidor falhou)")
        else:
            print(f"[DEBUG_MONITORING] Servidor atual: {current_server.id} (Status: {current_server.status})")

        # Encontrar servidor de destino
        target_server = find_migration_target(
            user, 
            service, 
            current_server, 
            reason, 
            current_step,
            reliability_value=criteria_data.get("reliability_value")  # ← NOVO PARÂMETRO
        )
        
        if target_server and target_server.available:
            if initiate_service_migration(service, target_server, reason, current_step):
               pass
            else:
                # Registrar falha na tentativa
                register_failed_migration_attempt(service.id, target_server.id, current_step)
        else:
            if not current_server or not current_server.available:
                # Servidor falhou E não há alternativa - DESPROVISIONAMENTO
                print(f"[LOG] Servidor atual falhou e sem alternativas - movendo ou mantendo na fila de espera")
               
               # Adicionar à fila de espera com alta prioridade (falha de servidor)
                priority_score = 999.0  # Prioridade máxima para falhas de servidor
                add_to_waiting_queue(user, app, service, priority_score, reason="server_failed")
     
            else:
                print(f"[DEBUG_MONITORING] Sem servidor disponível - mantendo no servidor atual {current_server.id}")
                # Se tinha candidatos mas nenhum funcionou, limpar bloqueios
                # (Para permitir retry no próximo step se a situação melhorar)
                if service.id in _failed_target_attempts:
                    # Manter bloqueios de menos de 3 steps atrás
                    cutoff_step = current_step - 3
                    _failed_target_attempts[service.id] = {
                        srv_id: step for srv_id, step in _failed_target_attempts[service.id].items()
                        if step > cutoff_step
                    }

def find_migration_target(user, service, current_server, migration_reason, current_step, reliability_value=None):
    """Encontra o melhor servidor de destino para migração com LÓGICA DE ESTADOS (SLA Binário)."""
    
    # 1. Identificar servidor atual com segurança
    current_server_id = current_server.id if current_server else None
    
    # 2. Obter candidatos (Nota: geralmente inclui o servidor atual se ele estiver disponível)
    available_servers = get_host_candidates(user, service)
    
    if not available_servers:
        return None
        
    # Recuperar metadados do servidor atual para comparação (ANTES de filtrar)
    current_server_metadata = next((s for s in available_servers if s["object"].id == current_server_id), None)

    # Adicionar reliability_value aos metadados
    if current_server_metadata and reliability_value is not None:
        current_server_metadata["reliability_value"] = reliability_value
    
    # 3. FILTRO RÍGIDO: Remover o servidor atual da lista de candidatos para migração
    migration_candidates = [
        candidate for candidate in available_servers
        if current_server_id is None or candidate["object"].id != current_server_id
    ]

    # ❌ Bloquear retentativas consecutivas para destinos que falharam recentemente
    failed_for_service = _failed_target_attempts.get(service.id, {})
    migration_candidates = [
        c for c in migration_candidates
        if failed_for_service.get(c["object"].id) is None
        or (current_step - failed_for_service[c["object"].id]) > 1
    ]
    
    if not migration_candidates:
        # print(f"[LOG] ⚠️  Sem candidatos alternativos (apenas o atual disponível)")
        return None
    
    # Obter SLA
    app_id = str(service.application.id)
    delay_sla = user.delay_slas[app_id]
    
    # 4. Ordenar candidatos pela lógica ponderada
    migration_candidates = sorted(migration_candidates, key=lambda s: s["trust_cost"]) # Ordenação preliminar
    migration_candidates = sort_host_candidates(migration_candidates, delay_sla=delay_sla, reason=migration_reason)
    
    best_candidate = migration_candidates[0]
    best_server = best_candidate["object"]
    
    # Se o servidor atual não existe ou falhou, aceita imediatamente o melhor disponível (Modo Recuperação)
    if migration_reason == "server_failed" or current_server is None or not current_server.available:
        if best_server.has_capacity_to_host(service):
            print(f"[LOG] ✅ Migração de RECUPERAÇÃO aceita para {best_server.id}")
            _failed_target_attempts.get(service.id, {}).pop(best_server.id, None)
            return best_server
        return None

    # ==============================================================================
    # NOVA LÓGICA DE DECISÃO BASEADA EM ESTADOS (STAY vs GO)
    # ==============================================================================
    
    if not current_server_metadata:
        # Se não conseguimos métricas do atual (raro), confiamos na ordenação e migramos
        if best_server.has_capacity_to_host(service):
            return best_server
        return None

    # Avaliar Estados de Delay
    current_violates_sla = current_server_metadata["overall_delay"] > delay_sla
    candidate_violates_sla = best_candidate["overall_delay"] > delay_sla
    
    # Avaliar Estados de Confiança (Trust Cost menor é melhor)
    current_trust = current_server_metadata["trust_cost"]
    candidate_trust = best_candidate["trust_cost"]
    
    # -------------------------------------------------------------------------
    # CASO 1: PRIORIDADE MAXIMA (Predicted Failure) - SOBREVIVÊNCIA
    # -------------------------------------------------------------------------
    if migration_reason == "predicted_failure":
        # Se for falha iminente, ignoramos SLA. Só precisamos ir para um lugar mais seguro.
        if candidate_trust < (current_trust * 0.99):
             if best_server.has_capacity_to_host(service):
                print(f"[LOG] 🚨 Migração de EMERGÊNCIA: Fugindo da falha prevista.")
                return best_server
        return None

    # -------------------------------------------------------------------------
    # CASO 2: PREVENÇÃO (Low Reliability) - WAIT STRATEGY ADAPTATIVA
    # -------------------------------------------------------------------------
    if migration_reason == "low_reliability":
        
        # ✅ NOVO: Calcular nível de risco do servidor atual
        current_reliability = current_server_metadata.get("reliability_value", 100)  # Valor de R(t)
        
        # ✅ DEFINIR LIMITE DE RISCO CRÍTICO
        # Se a confiabilidade atual cair abaixo deste limite, FORÇA migração mesmo violando SLA
        CRITICAL_RELIABILITY_THRESHOLD = 50.0  # 60% = risco muito alto
        
        is_critical_situation = current_reliability < CRITICAL_RELIABILITY_THRESHOLD
        
        # ═════════════════════════════════════════════════════════════
        # CENÁRIO 1: Situação NÃO CRÍTICA (R > 60%)
        # ═════════════════════════════════════════════════════════════
        if not is_critical_situation:
            # REGRA DE OURO: Se o destino viola SLA, NÃO VAMOS (Wait Strategy)
            # Preferimos arriscar ficar no servidor atual (que está "amarelo") por mais alguns steps
            if candidate_violates_sla:
                if not current_violates_sla:
                    # Estamos bem de SLA agora, não vamos estragar isso por um risco estatístico leve.
                    print(f"[LOG] 🛑 Cancelada (Wait Strategy): Destino seguro viola SLA. Mantendo risco no atual (R={current_reliability:.1f}%).")
                    return None
                
                # Se JÁ estamos violando SLA e vamos para outro que também viola:
                # Só vale a pena se o ganho de segurança for brutal.
                # Caso contrário, evita overhead de migração.
                if candidate_trust >= (current_trust * 0.95):  # Ganho < 5%
                    print(f"[LOG] 🛑 Cancelada (Wait Strategy): Ambos violam SLA e ganho de segurança é marginal.")
                    return None
            
            # REGRA DE MELHORIA: Só migra se houver ganho real de confiabilidade (>5%)
            if candidate_trust < (current_trust * 0.95):
                if best_server.has_capacity_to_host(service):
                    print(f"[LOG] ✅ Migração PREVENTIVA aceita: Melhora confiabilidade ({current_trust:.2f}->{candidate_trust:.2f})")
                    return best_server
            
            print(f"[LOG] 🛑 Cancelada (Low Gain): Ganho de confiabilidade marginal ou destino insuficiente.")
            return None
        
        # ═════════════════════════════════════════════════════════════
        # CENÁRIO 2: Situação CRÍTICA (R < 60%) - MIGRAÇÃO FORÇADA
        # ═════════════════════════════════════════════════════════════
        else:
            print(f"[LOG] 🚨 SITUAÇÃO CRÍTICA: Confiabilidade atual={current_reliability:.1f}% < {CRITICAL_RELIABILITY_THRESHOLD}%")
            
            # ✅ EM SITUAÇÃO CRÍTICA: Aceitar destino que viola SLA SE melhorar confiabilidade
            if candidate_trust < current_trust:
                if best_server.has_capacity_to_host(service):
                    if candidate_violates_sla:
                        print(f"[LOG] ⚠️ Migração de EMERGÊNCIA: Destino viola SLA mas EVITA FALHA IMINENTE")
                        print(f"          Confiabilidade: {current_trust:.2f} → {candidate_trust:.2f}")
                        print(f"          Delay previsto: {best_candidate['overall_delay']:.1f}ms (SLA: {delay_sla}ms)")
                    else:
                        print(f"[LOG] ✅ Migração de EMERGÊNCIA: Destino RESOLVE SLA E melhora segurança")
                    
                    return best_server
            
            # ✅ Se nenhum candidato melhora confiabilidade, aceitar o melhor disponível (último recurso)
            print(f"[LOG] ⚠️ ÚLTIMO RECURSO: Nenhum candidato melhora confiabilidade, usando melhor disponível")
            if best_server.has_capacity_to_host(service):
                return best_server
            
            return None

    # -------------------------------------------------------------------------
    # CASO 3: PERFORMANCE (Delay Violation)
    # -------------------------------------------------------------------------
    if migration_reason == "delay_violation":
        # A lógica aqui permanece: só migra se resolver o problema ou melhorar muito
        if not current_violates_sla:
            return None # Falso positivo do trigger anterior
            
        if not candidate_violates_sla:
            # Resolve o problema!
            if best_server.has_capacity_to_host(service):
                return best_server
        
        elif best_candidate["overall_delay"] < (current_server_metadata["overall_delay"] * 0.70):
             # Melhora parcial significativa
             if best_server.has_capacity_to_host(service):
                 return best_server
        
        return None
            
    # Fallback para outros motivos
    if best_server.has_capacity_to_host(service):
        return best_server
        
    return None
    


def initiate_service_migration(service, target_server, reason, current_step):
    """Inicia migração com rastreamento CORRETO de Cold vs Hot Migrations."""
    
    # ✅ DEBUG IMEDIATO - FORÇAR razão se vazia
    if not reason or reason == "unknown":
        # Tentar inferir razão baseado no contexto
        if service.server and not service.server.available:
            reason = "server_failed"
            print(f"[INITIATE_MIGRATION] ⚠️ Razão vazia! Inferido 'server_failed' (servidor indisponível)")
        else:
            reason = "unknown_forced"
            print(f"[INITIATE_MIGRATION] ⚠️ Razão vazia! Forçando 'unknown_forced'")
    
    print(f"\n[INITIATE_MIGRATION] === INÍCIO ===")
    print(f"[INITIATE_MIGRATION] Serviço: {service.id}")
    print(f"[INITIATE_MIGRATION] Target: {target_server.id}")
    print(f"[INITIATE_MIGRATION] Reason: '{reason}'")
    print(f"[INITIATE_MIGRATION] Current Step: {current_step}")
    
    original_server = service.server

    normalized_reason, original_reason, is_cold_migration, is_recovery_after_prevention = (
        classify_migration_reason(original_server, reason)
    )
    reason = normalized_reason

    # ✅ TRACKING de qualidade (centralizado)
    if reason in ["low_reliability", "predicted_failure"] and original_server:
        _prediction_quality_metrics["proactive_migrations"].append({
            "service_id": service.id,
            "server_id": original_server.id,
            "step": current_step,
            "reason": reason,
            "validated": False,
            "validation_window": 150,
        })
    elif reason == "server_failed" and is_cold_migration:
        _prediction_quality_metrics["false_negatives"] += 1
    
    
    # ==============================================================================
    # TRACKING DE QUALIDADE DE PREVISÃO
    # ==============================================================================
    
    try:
        # ✅ 1. CHAMAR provision() PRIMEIRO (isso cria a migração)
        print(f"[INITIATE_MIGRATION] Chamando service.provision()...")
        service.provision(target_server=target_server)
        print(f"[INITIATE_MIGRATION] provision() executado")
        
        # ✅ 2. VERIFICAR se migração foi criada
        if not hasattr(service, '_Service__migrations'):
            raise Exception(f"Serviço {service.id} não possui atributo __migrations após provision()")
        
        if len(service._Service__migrations) == 0:
            raise Exception(f"Serviço {service.id} possui __migrations vazio após provision()")
        
        print(f"[INITIATE_MIGRATION] Total de migrações: {len(service._Service__migrations)}")
        
        # ✅ 3. Pegar migração recém-criada
        migration = service._Service__migrations[-1]
        
        print(f"[INITIATE_MIGRATION] Migração antes de adicionar flags:")
        print(f"                     Status: {migration.get('status', 'N/A')}")
        print(f"                     Origin: {migration.get('origin').id if migration.get('origin') else None}")
        print(f"                     Target: {migration.get('target').id if migration.get('target') else None}")
        print(f"                     migration_reason (antes): {migration.get('migration_reason', 'N/A')}")
        
        # ✅ 4. ADICIONAR FLAGS (SEMPRE)
        migration["migration_reason"] = reason
        migration["original_migration_reason"] = original_reason  # ✅ GARANTIR QUE NUNCA SEJA None
        migration["is_cold_migration"] = is_cold_migration
        migration["is_recovery_after_prevention"] = is_recovery_after_prevention  # ✅ NOVA FLAG
        migration["relationships_created_by_algorithm"] = True
        migration["origin_cleanup_pending"] = True
        migration["downtime_start_step"] = None
        migration["was_available_before_migration"] = service._available
        
        # ✅ VALIDAÇÃO FINAL
        if not migration["original_migration_reason"]:
            print(f"[INITIATE_MIGRATION] ⚠️⚠️⚠️ ALERTA: original_migration_reason AINDA É None!")
            migration["original_migration_reason"] = "unknown_error"
        
        print(f"[INITIATE_MIGRATION] FLAGS ADICIONADAS:")
        print(f"                     migration_reason: '{migration['migration_reason']}'")
        print(f"                     original_migration_reason: '{migration['original_migration_reason']}'")
        print(f"                     is_cold_migration: {migration['is_cold_migration']}")
        print(f"                     is_recovery_after_prevention: {migration['is_recovery_after_prevention']}")
        
        # ==============================================================================
        # LIVE MIGRATION LOGIC
        # ==============================================================================
        if original_server is None or not original_server.available:
            print(f"[INITIATE_MIGRATION] Modo: COLD MIGRATION (origem indisponível)")
            service._available = False
        else:
            print(f"[INITIATE_MIGRATION] Modo: LIVE MIGRATION (mantendo disponibilidade)")
            service._available = True
        
        print(f"[INITIATE_MIGRATION] ✓ Migração registrada com sucesso")
        print(f"[INITIATE_MIGRATION] === FIM ===\n")
        
        # ✅ LIMPAR bloqueios de retry para este serviço
        clear_failed_attempts_for_service(service.id)
        
        return True
        
    except Exception as e:
        print(f"[INITIATE_MIGRATION] ✗ ERRO EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        
        # Reverter APENAS destino
        service.server = original_server
        if service in target_server.services:
            target_server.services.remove(service)
        
        # ✅ Registrar falha
        register_failed_migration_attempt(service.id, target_server.id, current_step)
        
        return False
        
    except Exception as e:
        print(f"[INITIATE_MIGRATION] ✗ ERRO EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        
        # Reverter APENAS destino
        service.server = original_server
        if service in target_server.services:
            target_server.services.remove(service)
        
        # ✅ Registrar falha
        register_failed_migration_attempt(service.id, target_server.id, current_step)
        
        return False


def update_application_delays(current_step):
    """Atualiza delays considerando disponibilidade REAL."""
    global _raw_latencies

    print()
    print("=" * 70)
    print(f"[DEBUG_DELAYS] === ATUALIZANDO DELAYS - STEP {current_step} ===")
    print("=" * 70)
    
    update_all_user_delays(current_step)
    
    # ✅ Coletar latências para análise (mantido)
    global _raw_latencies
    for user in User.all():
        for app in user.applications:
            if is_user_accessing_application(user, app, current_step):
                current_val = user.delays.get(str(app.id), 0)
                if current_val > 0 and current_val != float('inf'):
                    _raw_latencies.append(current_val)


def check_service_availability_after_service_step(service):
    """
    Verifica disponibilidade REAL do serviço APÓS service_step() executar.
    
    REGRAS:
    1. Se NÃO tem migração: disponível SE server.available E service._available
    2. Se TEM migração ativa (end=None): INDISPONÍVEL
    3. Se migração finalizou (end!=None) NO STEP ANTERIOR: DISPONÍVEL
    4. Se migração finalizou NO STEP ATUAL: AINDA INDISPONÍVEL
    
    Returns:
        bool: True se disponível, False caso contrário
    """
    
    # Caso 1: Sem migração
    if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
        return service.server and service.server.status == "available" and service._available
    
    last_migration = service._Service__migrations[-1]
    
    # Caso 2: Migração ativa
    if last_migration["end"] is None:
        # ✅ NOVA LÓGICA: Se estiver rodando na origem (Live Migration) e origem disponível
        if service.server == last_migration.get("origin"):
            if service.server and service.server.status == "available":
                return True
        
        return False  # Indisponível (Cold migration ou Cutover)
    
    # Caso 3 e 4: Migração finalizada
    current_step = service.model.schedule.steps + 1
    migration_ended_at = last_migration["end"]
    
    # Se finalizou no step atual, service_step() ACABOU DE FINALIZAR
    # Mas delays só devem ser atualizados NO PRÓXIMO STEP
    if migration_ended_at == current_step:
        return False  # AINDA INDISPONÍVEL (acabou de finalizar)
    
    # Se finalizou em step anterior, agora está disponível
    return service.server and service.server.status == "available" and service._available


def check_and_deprovision_inactive_services(current_step):
    """
    Verifica e desprovisiona serviços inativos.
    ✅ CORREÇÃO: Órfãos de usuários ATIVOS vão para fila de migração ao invés de serem limpos.
    """
    print()
    print("=" * 70)
    print(f"[DEBUG_DEPROVISION] === VERIFICANDO SERVIÇOS INATIVOS E ÓRFÃOS - STEP {current_step} ===")
    print("=" * 70)
    
    services_to_deprovision = []
    orphans_cleaned = 0
    orphans_to_migrate = 0  # ✅ NOVO: Contar órfãos que vão para fila
    servers_to_recalculate = set()
    
    # ═══════════════════════════════════════════════════════════════
    # PARTE 1: LIMPAR SERVIÇOS ÓRFÃOS DE TODOS OS SERVIDORES
    # ═══════════════════════════════════════════════════════════════
    for server in EdgeServer.all():
        services_to_remove = []
        
        for service in list(server.services):
            should_remove = False
            removal_reason = ""
            
            # Caso 1: Serviço aponta para OUTRO servidor
            if service.server and service.server != server:
                should_remove = True
                removal_reason = f"aponta para servidor {service.server.id}"
            
            # Caso 2: Serviço sem aplicação ou usuário
            elif not service.application or not service.application.users:
                should_remove = True
                removal_reason = "sem aplicação/usuário válido"
            
            # Caso 3: Servidor disponível MAS recursos zerados E tem serviços
            elif (server.available and 
                  server.cpu_demand == 0 and 
                  server.memory_demand == 0 and 
                  len(server.services) > 0):
                should_remove = True
                removal_reason = "servidor disponível mas recursos zerados"
            
            # ✅ CORREÇÃO CASO 4: Servidor indisponível E serviço não está em migração ativa
            # NOVA LÓGICA: Verificar se usuário ainda está acessando
            elif not server.available and service.server == server:
                in_active_migration = False
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]
                    if last_migration.get("end") is None:
                        in_active_migration = True
                
                # ✅ NOVO: Se não está em migração E usuário ainda acessa, NÃO LIMPAR
                if not in_active_migration:
                    app = service.application
                    if app and app.users:
                        user = app.users[0]
                        is_accessing = is_user_accessing_application(user, app, current_step)
                        
                        if is_accessing:
                            # ✅ USUÁRIO ATIVO: Adicionar à fila de migração ao invés de limpar
                            print(f"[DEBUG_DEPROVISION] Servidor {server.id}: Serviço {service.id} órfão mas USUÁRIO ATIVO")
                            print(f"                    Adicionando à fila de migração (server_failed)")
                            
                            # Adicionar à fila de espera com prioridade MÁXIMA
                            add_to_waiting_queue(user, app, service, priority_score=999.0, reason="server_failed")
                            
                            # Marcar para remoção da lista do servidor morto
                            should_remove = True
                            removal_reason = f"servidor {server.id} falhou - migrando para fila"
                            orphans_to_migrate += 1
                        else:
                            # ✅ USUÁRIO INATIVO: Limpar normalmente
                            should_remove = True
                            removal_reason = f"servidor {server.id} indisponível sem migração ativa (usuário inativo)"
            
            if should_remove:
                services_to_remove.append((service, removal_reason))
        
        # Executar remoção de órfãos
        for service, reason in services_to_remove:
            server.services.remove(service)
            orphans_cleaned += 1
            servers_to_recalculate.add(server)
            
            if orphans_cleaned <= 5:
                print(f"[DEBUG_DEPROVISION] Servidor {server.id}: Removido órfão {service.id} ({reason})")
    
    if orphans_cleaned > 0:
        print(f"[DEBUG_DEPROVISION] {orphans_cleaned} serviços órfãos removidos")
        if orphans_to_migrate > 0:
            print(f"[DEBUG_DEPROVISION] ✅ {orphans_to_migrate} órfãos ATIVOS adicionados à fila de migração")
    
    # ═══════════════════════════════════════════════════════════════
    # ✅ NOVO: RECALCULAR DEMANDA DOS SERVIDORES AFETADOS
    # ═══════════════════════════════════════════════════════════════
    for server in servers_to_recalculate:
        # Recalcular demanda a partir dos serviços reais
        correct_cpu_demand = sum(s.cpu_demand for s in server.services if s.server == server)
        correct_memory_demand = sum(s.memory_demand for s in server.services if s.server == server)
        
        if server.cpu_demand != correct_cpu_demand or server.memory_demand != correct_memory_demand:
            print(f"[DEBUG_DEPROVISION] Servidor {server.id}: Recalculando demanda")
            print(f"                    CPU: {server.cpu_demand} → {correct_cpu_demand}")
            print(f"                    MEM: {server.memory_demand} → {correct_memory_demand}")
            
            server.cpu_demand = correct_cpu_demand
            server.memory_demand = correct_memory_demand
    
    # ═══════════════════════════════════════════════════════════════
    # PARTE 2: IDENTIFICAR SERVIÇOS INATIVOS PARA DESPROVISIONAMENTO
    # ═══════════════════════════════════════════════════════════════
    for service in Service.all():
        app = service.application
        
        if not app or not app.users:
            continue
        
        user = app.users[0]
        app_id = str(app.id)
        
        is_accessing = is_user_accessing_application(user, app, current_step)
        
        if not is_accessing and service.server:
            server = service.server
            
            # PROTEÇÃO: Servidor falhou e relacionamento já limpo
            if not server.available and service not in server.services:
                print(f"[DEBUG_DEPROVISION] Serviço {service.id}: Servidor {server.id} falhou - limpeza completa")
                
                service.server = None
                service._available = False
                user.delays[app_id] = 0
                
                # ✅ NÃO precisa ajustar demanda aqui porque já foi recalculada acima
                
                # Limpar migração pendente
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]
                    if last_migration.get("end") is None:
                        cancel_service_migration(service, reason="server_failed_and_user_stopped")
                
                continue
            
            services_to_deprovision.append({
                "service": service,
                "app": app,
                "server": server,
                "has_active_migration": (hasattr(service, '_Service__migrations') and 
                                        len(service._Service__migrations) > 0 and
                                        service._Service__migrations[-1].get("end") is None)
            })
    
    if not services_to_deprovision:
        if orphans_cleaned == 0:
            print(f"[DEBUG_DEPROVISION] Nenhum serviço inativo ou órfão para processar")
        print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")
        return
    
    print(f"[DEBUG_DEPROVISION] {len(services_to_deprovision)} serviços inativos identificados")
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 1: CANCELAR MIGRAÇÕES ATIVAS
    # ═══════════════════════════════════════════════════════════════
    migrations_cancelled = 0
    for item in services_to_deprovision:
        if item["has_active_migration"]:
            if cancel_service_migration(item["service"], reason="user_stopped_accessing"):
                migrations_cancelled += 1
    
    if migrations_cancelled > 0:
        print(f"[DEBUG_DEPROVISION] {migrations_cancelled} migrações canceladas")
        print(f"[DEBUG_DEPROVISION] Desprovisionamento será feito no próximo step")
        print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")
        return
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 2: DESPROVISIONAR SERVIÇOS
    # ═══════════════════════════════════════════════════════════════
    deprovisioned_count = 0
    for item in services_to_deprovision:
        service = item["service"]
        app = item["app"]
        server = item["server"]
        user = app.users[0]
        
        print(f"\n[DEBUG_DEPROVISION] Serviço {service.id} (App {app.id}) - desprovisionando")
        print(f"[DEPROVISION] Desprovisionando serviço {service.id} do servidor {server.id}")
        
        # VERIFICAÇÃO: Se ainda tem migração ativa (anomalia)
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            last_migration = service._Service__migrations[-1]
            
            if last_migration.get("end") is None:
                print(f"[DEPROVISION] ⚠️ ANOMALIA: Migração ativa - cancelando antes de desprovisionar")
                cancel_service_migration(service, reason="user_stopped_accessing")
        
        # Liberar recursos SOMENTE se servidor está disponível
        if server.available:
            server.cpu_demand = max(0, server.cpu_demand - service.cpu_demand)
            server.memory_demand = max(0, server.memory_demand - service.memory_demand)
            print(f"[DEPROVISION] Recursos liberados")
        else:
            print(f"[DEPROVISION] Recursos NÃO liberados (servidor indisponível)")
        
        # Remover serviço da lista do servidor
        if service in server.services:
            server.services.remove(service)
            print(f"[DEPROVISION] ✓ Removido da lista do servidor {server.id}")
        
        # Limpar relacionamento
        service.server = None
        service._available = False
        
        # Limpar delay do usuário
        app_id = str(app.id)
        user.delays[app_id] = 0
        
        print(f"[DEPROVISION] ✓ Desprovisionamento concluído")
        deprovisioned_count += 1
    
    print(f"[DEBUG_DEPROVISION] {deprovisioned_count} serviços desprovisionados")
    print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")


def mark_proactive_migration_canceled(service_id, server_id, current_step, reason):
    """Marca uma migração preventiva como cancelada (não conta TP/FP)."""
    for item in _prediction_quality_metrics["proactive_migrations"]:
        if item.get("service_id") == service_id and item.get("server_id") == server_id:
            item["canceled"] = True
            item["validated"] = True
            item["outcome"] = "canceled"
            item["canceled_reason"] = reason
            item["validated_at"] = current_step
            return True
    return False


def cancel_service_migration(service, reason):
    """
    Cancela uma migração em andamento e interrompe downloads relacionados.
    """
    if not hasattr(service, '_Service__migrations') or not service._Service__migrations:
        return False
    
    migration = service._Service__migrations[-1]
    
    if migration.get("end") is not None:
        return False
    
    current_step = service.model.schedule.steps + 1
    target_server = migration.get("target")
    
    print(f"[CANCEL_MIGRATION] Cancelando migração do serviço {service.id}")
    print(f"                   Razão: {reason}")
    print(f"                   Target: {target_server.id if target_server else 'None'}")
    
    # ✅ OBTER IMAGEM DO SERVIÇO
    service_image = None
    if hasattr(service, 'image_digest') and service.image_digest:
        from edge_sim_py.components.container_image import ContainerImage
        service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
    
    interrupted_flows = []
    layers_to_remove = []
    
    if target_server and service_image:
        # ✅ 1. INTERROMPER FLUXOS NA download_queue
        for flow in list(target_server.download_queue):
            if (hasattr(flow, 'metadata') and 
                flow.metadata.get('type') == 'layer' and
                flow.target == target_server):
                
                layer = flow.metadata.get('object')
                
                if layer and hasattr(layer, 'digest') and layer.digest in service_image.layers_digests:
                    flow.status = "interrupted"
                    flow.data_to_transfer = 0
                    interrupted_flows.append(flow)
                    print(f"[CANCEL_MIGRATION] ✓ Fluxo interrompido: Layer {layer.digest[:8]}")
        
        # ✅ 2. LIMPAR waiting_queue
        for layer in list(target_server.waiting_queue):
            if hasattr(layer, 'digest') and layer.digest in service_image.layers_digests:
                layers_to_remove.append(layer)
        
        for layer in layers_to_remove:
            target_server.waiting_queue.remove(layer)
            print(f"[CANCEL_MIGRATION] ✓ Camada removida da waiting_queue: {layer.digest[:8]}")
    
    # ✅ 3. LIMPAR FLUXOS INTERROMPIDOS DA download_queue
    if target_server:
        for flow in interrupted_flows:
            if flow in target_server.download_queue:
                target_server.download_queue.remove(flow)
                print(f"[CANCEL_MIGRATION] ✓ Fluxo removido da download_queue")
    
    print(f"[CANCEL_MIGRATION] Total de fluxos interrompidos e removidos: {len(interrupted_flows)}")
    print(f"[CANCEL_MIGRATION] Camadas removidas da waiting_queue: {len(layers_to_remove)}")
    
    # 4. Marcar migração como interrompida
    migration["status"] = "interrupted"
    migration["end"] = current_step
    migration["interruption_reason"] = reason

    # Se cancelado por usuário, não conta como FP/TP
    origin_server = migration.get("origin")
    if reason in ["user_stopped_accessing", "server_failed_and_user_stopped"]:
        mark_proactive_migration_canceled(
            service_id=service.id,
            server_id=origin_server.id if origin_server else None,
            current_step=current_step,
            reason=reason
        )
    
    # 5. Resetar flags de controle
    service.being_provisioned = False
    
    # 6. Decrementar contadores de migração
    if target_server and hasattr(target_server, 'ongoing_migrations'):
        target_server.ongoing_migrations = max(0, target_server.ongoing_migrations - 1)
    
    origin_server = migration.get("origin")
    if origin_server and hasattr(origin_server, 'ongoing_migrations'):
        origin_server.ongoing_migrations = max(0, origin_server.ongoing_migrations - 1)
    
    print(f"[CANCEL_MIGRATION] ✓ Migração cancelada com sucesso")
    
    return True

# ============================================================================
# NEW REQUEST PROVISIONING
# ============================================================================

def provision_new_requests(current_step):
    """Provisiona novas requisições de aplicações."""
    print()
    print("=" * 70)
    print(f"[DEBUG_NEW_REQUESTS] === PROVISIONAMENTO DE NOVAS REQUISIÇÕES - STEP {current_step} ===")
    print("=" * 70)
    
    # Coletar aplicações com novas requisições
    apps_metadata = collect_new_request_metadata(current_step)
    
    if apps_metadata:
        # Sort apps by priority
        sorted_apps = sort_applications_by_priority(apps_metadata)  
        all_apps_metadata = apps_metadata 

        # ✅ NOVA ESTRUTURA: Contador efêmero para o step atual
        # Rastreia quantos serviços foram alocados em cada servidor NESTE loop
        ephemeral_load_tracker = {} # {server_id: count}

        for app_metadata in sorted_apps:
            process_application_request(app_metadata, all_apps_metadata, ephemeral_load_tracker)
    else:
        print("[DEBUG_NEW_REQUESTS] Nenhuma nova requisição neste step.")
    
    print(f"[DEBUG_NEW_REQUESTS] === FIM PROVISIONAMENTO DE NOVAS REQUISIÇÕES ===\n")

def collect_new_request_metadata(current_step):
    """Coleta metadados de aplicações com novas requisições."""
    apps_metadata = []
    
    for user in User.all():
        if is_making_request(user, current_step):
            for app in user.applications:
                app_attrs = {
                    "object": app,
                    "delay_sla": app.users[0].delay_slas[str(app.id)],
                    "delay_cost": get_application_delay_cost(app),
                    "intensity_score": get_application_access_intensity_score(app),
                    "demand_resource": get_normalized_demand(app.services[0]),
                    "delay_urgency": get_delay_urgency(app, user)
                }
                
                apps_metadata.append(app_attrs)
    
    return apps_metadata

def sort_applications_by_priority(apps_metadata):
    """Ordena aplicações por prioridade usando normalização."""
    min_and_max_app = find_minimum_and_maximum(metadata=apps_metadata)
  
    return sorted(
        apps_metadata, 
        key=lambda app: (
        get_norm(metadata=app, attr_name="delay_cost", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        get_norm(metadata=app, attr_name="intensity_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        (1 - get_norm(metadata=app, attr_name="demand_resource", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]))
    ), reverse=True
    )

def process_application_request(app_metadata, all_apps_metadata, ephemeral_load_tracker=None):
    """Processa requisição de uma aplicação específica."""
    app = app_metadata["object"]
    user = app.users[0]
    service = app.services[0]
    
    print(f"\n[LOG] Processando aplicação {app.id}:")
    print(f"      Delay Cost: {app_metadata['delay_cost']:.4f}")
    print(f"      SLA: {app_metadata['delay_sla']}")
    
    # Verificar se está na fila de espera
    if is_application_in_waiting_queue(app.id):
        print(f"[LOG] Aplicação {app.id} já está na fila de espera")
        return
    
    # Tentar provisionar
    if not try_provision_service(user, app, service, ephemeral_load_tracker=ephemeral_load_tracker):
        # Adicionar à fila de espera se falhou
        #min_and_max_app = find_minimum_and_maximum(metadata=all_apps_metadata)
        print(f"[LOG] Adicionando aplicação {app.id} à fila de espera")
        priority_score = app_metadata["delay_urgency"]
        add_to_waiting_queue(user, app, service, priority_score, reason="initial_provisioning")

def try_provision_service(user, app, service, reason=None, ephemeral_load_tracker=None):
    """Tenta provisionar um serviço com relacionamentos antecipados."""
    
    edge_servers = get_host_candidates(user=user, service=service)
    
    if not edge_servers:
        print(f"[LOG] Nenhum servidor disponível para aplicação {app.id}")
        return False
    
    context = reason if reason else "provisioning"
    delay_sla = user.delay_slas[str(app.id)]
    
    # ✅ Passar o tracker para a ordenação
    edge_servers = sort_host_candidates(
        edge_servers, 
        delay_sla=delay_sla, 
        reason=context, 
        ephemeral_load_tracker=ephemeral_load_tracker
    )
    
    for edge_server_metadata in edge_servers:
        edge_server = edge_server_metadata["object"]
        
        if edge_server.has_capacity_to_host(service):
            print(f"[LOG] ✓ Provisionando aplicação {app.id} no servidor {edge_server.id}")
        
        if edge_server.has_capacity_to_host(service):
            print(f"[LOG] ✓ Provisionando aplicação {app.id} no servidor {edge_server.id}")
            print(f"      Delay previsto: {edge_server_metadata['overall_delay']}")
            print(f"      SLA: {user.delay_slas[str(app.id)]}")
            print(f"      Viola SLA: {'SIM' if edge_server_metadata['sla_violations'] else 'NÃO'}")
            
            # ✅ SALVAR estado original
            original_server = service.server
            
            try:
                # ✅ CHAMAR provision() PRIMEIRO
                service.provision(target_server=edge_server)

                # ✅ DEPOIS criar relacionamentos antecipados
                service.server = edge_server
                edge_server.services.append(service)

                # ✅ Marcar como INDISPONÍVEL
                service._available = False

                # ✅ ADICIONAR flags
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["relationships_created_by_algorithm"] = True

                    # ✅ LÓGICA CORRIGIDA DE RAZÃO
                    if original_server is None:
                        if reason == "server_failed":
                            migration["is_initial_provisioning"] = False
                            migration["migration_reason"] = "server_failed"
                        elif reason == "initial_provisioning":
                            migration["is_initial_provisioning"] = True
                            migration["migration_reason"] = "Initial Provisioning"
                        else:
                            migration["is_initial_provisioning"] = True
                            migration["migration_reason"] = "Initial Provisioning"
                    else:
                        migration["is_initial_provisioning"] = False
                        migration["migration_reason"] = reason if reason else "Reprovisioning (Forced)"

                    # ✅ NOVO: Classificação consolidada
                    normalized_reason, original_reason, is_cold_migration, is_recovery_after_prevention = (
                        classify_migration_reason(original_server, reason)
                    )
                    migration["original_migration_reason"] = original_reason
                    migration["is_cold_migration"] = is_cold_migration
                    migration["is_recovery_after_prevention"] = is_recovery_after_prevention

                    # ✅ TRACKING de qualidade também aqui (fila / recuperação)
                    if normalized_reason in ["low_reliability", "predicted_failure"] and original_server:
                        _prediction_quality_metrics["proactive_migrations"].append({
                            "service_id": service.id,
                            "server_id": original_server.id,
                            "step": user.model.schedule.steps + 1,
                            "reason": normalized_reason,
                            "validated": False,
                            "validation_window": 150,
                        })
                    elif normalized_reason == "server_failed" and is_cold_migration:
                        _prediction_quality_metrics["false_negatives"] += 1

                    print(f"[LOG] Provisionamento iniciado - Origin: {migration['origin'].id if migration['origin'] else 'None'}, Target: {migration['target'].id}")

                if ephemeral_load_tracker is not None:
                    count = ephemeral_load_tracker.get(edge_server.id, 0)
                    ephemeral_load_tracker[edge_server.id] = count + 1
                    
                return True
                
            except Exception as e:
                print(f"[LOG] ✗ Erro ao provisionar: {e}")
                import traceback
                traceback.print_exc()
                
                # Reverter
                service.server = original_server
                if service in edge_server.services:
                    edge_server.services.remove(service)
                
                # Tentar próximo servidor
                continue
    
    print(f"[LOG] ✗ Servidores sem capacidade para aplicação {app.id}")
    return False

def sort_host_candidates(edge_servers, delay_sla=None, reason="provisioning", ephemeral_load_tracker=None):
    """
    Ordena candidatos baseando-se na filosofia de SATISFAÇÃO DE SLA + OTIMIZAÇÃO DE RECURSOS.
    Inclui penalidade para carga efêmera (fila virtual).
    """
    if not edge_servers:
        return edge_servers
    
    # ✅ Pré-cálculo com Carga Virtual
    for s in edge_servers:
        server_obj = s.get("object")
        
        # Carga real atual
        current_queue = len(getattr(server_obj, "download_queue", [])) if server_obj else 0
        
        # Carga adicionada neste mesmo step (ainda não refletida no download_queue)
        added_load = 0
        if ephemeral_load_tracker and server_obj:
            added_load = ephemeral_load_tracker.get(server_obj.id, 0)
        
        # Fila Projetada
        projected_queue_size = current_queue + added_load
        
        # Atualizar estimativa de tempo nos metadados
        s["projected_queue_size"] = projected_queue_size
    
    # ✅ Pré-cálculo para normalização
    for s in edge_servers:
        s.setdefault("trust_cost", 0)
        s.setdefault("amount_of_uncached_layers", 0)
        s.setdefault("overall_delay", 0)
        s.setdefault("free_capacity", 0)
        s.setdefault("estimated_provisioning_time", 0)
        s.setdefault("total_uncached_mb", 0)
        
        server_obj = s.get("object")
        s["download_queue_size"] = len(getattr(server_obj, "download_queue", [])) if server_obj else 0

    min_and_max = find_minimum_and_maximum(metadata=edge_servers)

    max_queue = max([s["projected_queue_size"] for s in edge_servers]) if edge_servers else 1
    if max_queue == 0: max_queue = 1

    for s in edge_servers:
        s["trust_cost_norm"] = get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"])
        s["uncached_layers_norm"] = get_norm(metadata=s, attr_name="amount_of_uncached_layers", min=min_and_max["minimum"], max=min_and_max["maximum"])
        s["delay_norm"] = get_norm(metadata=s, attr_name="overall_delay", min=min_and_max["minimum"], max=min_and_max["maximum"])
        s["capacity_norm"] = 1 - get_norm(metadata=s, attr_name="free_capacity", min=min_and_max["minimum"], max=min_and_max["maximum"])
        
        s["provisioning_time_norm"] = get_norm(metadata=s, attr_name="estimated_provisioning_time", min=min_and_max["minimum"], max=min_and_max["maximum"])
        s["uncached_mb_norm"] = get_norm(metadata=s, attr_name="total_uncached_mb", min=min_and_max["minimum"], max=min_and_max["maximum"])
        s["queue_norm"] = s["projected_queue_size"] / max_queue

    # -------------------------------------------------------------------------
    # MODO 1: EMERGÊNCIA (CONFIABILIDADE / FALHA)
    # -------------------------------------------------------------------------
    if reason in ["low_reliability", "predicted_failure", "server_failed"]:
        return sorted(
            edge_servers,
            key=lambda s: (
                0 if (delay_sla and s["overall_delay"] <= delay_sla) else 1,
                s["trust_cost_norm"],
                s["provisioning_time_norm"],
                s["uncached_mb_norm"],
                s["delay_norm"]
            )
        )

    # -------------------------------------------------------------------------
    # MODO 2: PROVISIONAMENTO (Otimizado V2)
    # -------------------------------------------------------------------------
    # Correção: PRIORIZAR CACHE HIT (Zero Download) ACIMA DE FILA VAZIA.
    # Se total_uncached_mb == 0, a fila não importa (não entra na download_queue).
    if reason in ["provisioning", "initial_provisioning"]:
        return sorted(
            edge_servers,
            key=lambda s: (
                # 1. SLA Compliant (Binary)
                0 if (delay_sla and s["overall_delay"] <= delay_sla) else 1,
                
                # 2. CACHE HIT COMPLETE (Binary - CRÍTICO)
                # Se não precisa baixar nada, ganha de qualquer servidor que precise,
                # independente do tamanho da fila do outro.
                0 if s["total_uncached_mb"] == 0 else 1,
                
                # 3. COMBINAÇÃO DE FILA + TAMANHO (Apenas se precisar baixar)
                # Se ambos precisam baixar, usamos uma soma ponderada.
                # A fila (queue_norm) pesa 2x mais que o tamanho do arquivo,
                # pois esperar na fila trava o provisionamento completamente.
                (s["queue_norm"] * 2.0) + s["uncached_mb_norm"],
                
                # 4. Critérios de desempate
                s["trust_cost_norm"],
                s["capacity_norm"],
                s["overall_delay"]
            )
        )

    # -------------------------------------------------------------------------
    # MODO 3: OUTROS (ex.: delay_violation)
    # -------------------------------------------------------------------------
    return sorted(
        edge_servers,
        key=lambda s: (
            0 if (delay_sla and s["overall_delay"] <= delay_sla) else 1,
            # Para migração de delay, preferimos quem tem a imagem (rápido)
            s["uncached_mb_norm"], 
            s["trust_cost_norm"],
            s["capacity_norm"],
            s["overall_delay"]
        )
    )

# ============================================================================
# USER ACCESS PATTERN FUNCTIONS
# ============================================================================

def get_remaining_access_time(user, application, current_step):
    """Calcula tempo restante de acesso em steps."""
    app_id = str(application.id)
    
    if app_id not in user.access_patterns:
        return 0
    
    access_pattern = user.access_patterns[app_id]
    if not access_pattern.history:
        return 0
    
    last_access = access_pattern.history[-1]
    
    if not (last_access["start"] <= current_step <= last_access["end"]):
        return 0
    
    return last_access["end"] - current_step

def get_active_applications_with_remaining_time(user, current_step):
    """Retorna aplicações ativas com informações de tempo."""
    active_applications = []
    
    for application in user.applications:
        if is_user_accessing_application(user, application, current_step):
            remaining_time = get_remaining_access_time(user, application, current_step)
            
            app_id = str(application.id)
            last_access = user.access_patterns[app_id].history[-1]
            
            active_applications.append({
                "application": application,
                "remaining_time": remaining_time,
                "total_duration": last_access["duration"],
                "access_start": last_access["start"],
                "access_end": last_access["end"]
            })
    
    return active_applications


# ============================================================================
# WEIBULL DIAGNOSTICS (opcional - para análise)
# ============================================================================

def diagnose_weibull_estimations(current_step):
    """Diagnostica qualidade das estimações Weibull (executar periodicamente)."""
    
    print(f"\n{'='*70}")
    print(f"DIAGNÓSTICO DE ESTIMAÇÕES WEIBULL - STEP {current_step}")
    print(f"{'='*70}\n")
    
    for server in EdgeServer.all():
        if server.model_name == "Jetson TX2":
            continue  # Pular registry (sem falhas)
        
        params = get_cached_weibull_parameters(server, current_step)
        
        print(f"Servidor {server.id} ({server.model_name}):")
        print(f"  Shape (c):       {params['tbf_shape']:.4f}")
        print(f"  Scale (λ):       {params['tbf_scale']:.2f}")
        print(f"  MTBF estimado:   {params['mtbf_estimated']:.2f}")
        print(f"  Sample size:     {params['sample_size']}")
        print(f"  Quality:         {params['estimation_quality']}")
        
        # Interpretação do shape
        if params['tbf_shape'] < 1:
            interpretation = "Falhas infantis (burn-in)"
        elif abs(params['tbf_shape'] - 1.0) < 0.05:
            interpretation = "Taxa constante (exponencial)"
        else:
            interpretation = f"Desgaste (aging, β={params['tbf_shape']:.2f})"
        
        print(f"  Interpretação:   {interpretation}")
        
        # Calcular confiabilidade para alguns horizontes
        rel_24h = get_server_conditional_reliability_weibull(server, 24)
        rel_48h = get_server_conditional_reliability_weibull(server, 48)
        rel_72h = get_server_conditional_reliability_weibull(server, 72)
        
        print(f"  R(24h):          {rel_24h:.2f}%")
        print(f"  R(48h):          {rel_48h:.2f}%")
        print(f"  R(72h):          {rel_72h:.2f}%")
        print()
    
    print(f"{'='*70}\n")


_prediction_cache_by_step = {}
_CACHE_RETENTION_STEPS = 10

def _get_cached_predictions(server, horizon, current_step):
    """Cacheia predict_next_n_failures com limpeza automática."""
    global _prediction_cache_by_step
    
    # ✅ LIMPEZA: A cada 10 steps
    if current_step % 10 == 0:
        cutoff_step = current_step - _CACHE_RETENTION_STEPS
        keys_to_remove = [k for k in _prediction_cache_by_step.keys() if k[0] < cutoff_step]
        
        for key in keys_to_remove:
            del _prediction_cache_by_step[key]
        
        if keys_to_remove:
            print(f"[CACHE_CLEANUP] {len(keys_to_remove)} entradas antigas removidas (total: {len(_prediction_cache_by_step)})")
    
    # Cache normal
    key = (current_step, server.id, horizon)
    if key not in _prediction_cache_by_step:
        _prediction_cache_by_step[key] = predict_next_n_failures(server, n_failures=2, max_horizon=horizon)
    
    return _prediction_cache_by_step[key]



def _recalculate_prediction_quality_counters():
    """Recalcula TP/FP a partir dos registros validados (ignora cancelados)."""
    tp = 0
    fp = 0

    for item in _prediction_quality_metrics["proactive_migrations"]:
        if not item.get("validated", False):
            continue
        if item.get("canceled", False):
            continue

        outcome = item.get("outcome", "")
        if outcome == "server_failed_correctly_predicted":
            tp += 1
        elif outcome == "server_survived_validation_window":
            fp += 1

    _prediction_quality_metrics["true_positives"] = tp
    _prediction_quality_metrics["false_positives"] = fp


def validate_predictions(current_step):
    """
    Verifica se as migrações proativas se justificaram.
    CORREÇÃO CRÍTICA: Identificar Falsos Positivos (servidor NÃO falhou no prazo).
    """
    global _prediction_quality_metrics

    if current_step % 100 == 0:
        pending = sum(
            1 for item in _prediction_quality_metrics["proactive_migrations"]
            if not item.get("validated", False) and not item.get("canceled", False)
        )
        if pending > 0:
            print(f"[VALIDATE] Step {current_step}: {pending} previsões pendentes. "
                  f"(TP:{_prediction_quality_metrics['true_positives']} FP:{_prediction_quality_metrics['false_positives']})")

    validations_done = 0

    for item in _prediction_quality_metrics["proactive_migrations"]:
        if item.get("validated", False) or item.get("canceled", False):
            continue

        server_id = item.get("server_id")
        predicted_step = item.get("step")
        validation_window = item.get("validation_window", 150)

        # Se não temos servidor, finaliza para não contaminar estatística
        server = next((s for s in EdgeServer.all() if s.id == server_id), None)
        if not server:
            item["validated"] = True
            item["outcome"] = "server_missing"
            item["validated_at"] = current_step
            continue

        # Janela de validação
        start_valid = predicted_step - validation_window
        end_valid = predicted_step + validation_window

        # ✅ True Positive: servidor falhou dentro da janela
        if not server.available and start_valid <= current_step <= end_valid:
            item["validated"] = True
            item["outcome"] = "server_failed_correctly_predicted"
            item["validated_at"] = current_step
            validations_done += 1
            continue

        # ✅ False Positive: janela expirou e servidor continuou disponível
        if current_step > end_valid and server.available:
            item["validated"] = True
            item["outcome"] = "server_survived_validation_window"
            item["validated_at"] = current_step
            validations_done += 1
            continue

    _recalculate_prediction_quality_counters()

    if validations_done > 0:
        print(f"[VALIDATE] {validations_done} previsões validadas no step {current_step}")


# ============================================================================
# SAVE METRICS TO JSON
# ============================================================================

def save_final_metrics_to_json(output_dir="results", run_id=None):
    """Salva métricas finais em JSON para análise de sensibilidade."""
    import json
    import os
    
    # Garantir diretório
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    prov_mig_metrics = get_provisioning_and_migration_metrics()
    prediction_metrics = _prediction_quality_metrics
    
    # Calcular precisão e recall
    tp = prediction_metrics["true_positives"]
    fp = prediction_metrics["false_positives"]
    fn = prediction_metrics["false_negatives"]
    
    if tp + fp > 0:
        prediction_metrics["precision"] = (tp / (tp + fp)) * 100
    else:
        prediction_metrics["precision"] = 0.0 # Evitar 100% se não houve tentativas
    
    if tp + fn > 0:
        prediction_metrics["recall"] = (tp / (tp + fn)) * 100
    else:
        prediction_metrics["recall"] = 0.0
    
    # Métricas agregadas
    all_times = prov_mig_metrics.get("migration_times", {}).get("all_migrations", [])
    avg_migration_time = sum(all_times) / len(all_times) if all_times else 0
    
    total_downtime = prov_mig_metrics.get("migration_downtime", {}).get("total_steps", 0)
    avg_downtime_per_migration = total_downtime / len(all_times) if all_times else 0
    
    cold_analysis = prov_mig_metrics.get("cold_migration_analysis", {})
    recovery_times = cold_analysis.get("recovery_times", [])
    
    # ✅ CORREÇÃO DE TEMPO: Usar .get com fallback seguro e evitar divisão por zero
    model = Topology.first().model
    
    # ✅ CORREÇÃO: Usar o tempo de CPU acumulado medido internamente
    total_cpu_time = getattr(model, '_trust_edge_total_execution_time', 0.0)
    
    # Fallback para wall-clock time se CPU time for zero (ex: bug no timer)
    if total_cpu_time == 0:
        total_cpu_time = getattr(model, '_simulation_execution_time_seconds', 0)
    
    metrics = get_simulation_metrics()
    consolidated = metrics.get_consolidated_metrics()
    total_steps = consolidated.get("total_simulation_steps", 1)
    if total_steps == 0: total_steps = 1
    
    avg_step_time = total_cpu_time / total_steps

    from simulator.helper_functions import collect_all_sla_violations
    consolidated_sla = collect_all_sla_violations()
    avg_delay = consolidated_sla.get("avg_delay", 0)

    # Fallback: usa latências capturadas no runtime
    if avg_delay == 0 and _raw_latencies:
        avg_delay = sum(_raw_latencies) / len(_raw_latencies)

    all_metrics = {
        "parameters": {
            "window_size": getattr(model, '_trust_edge_window_size', 0),
            "reliability_threshold": getattr(model, '_trust_edge_reliability_threshold', 0),
            "delay_threshold": getattr(model, '_trust_edge_delay_threshold', 0),
        },
        "provisioning_and_migration": prov_mig_metrics,
        "prediction_quality": prediction_metrics,
        
        # ✅ Métricas de Execução corrigidas
        "execution": {
            "total_cpu_time_seconds": total_cpu_time,
            "avg_time_per_step_seconds": avg_step_time,
        },
        "sla": {
            "total_delay_sla_violations": consolidated["total_delay_sla_violations"],
            "total_perceived_downtime": consolidated["total_perceived_downtime"],
            "total_downtime_sla_violations": consolidated["total_downtime_sla_violations"],
            "avg_delay": avg_delay,
        },
        "infrastructure": {
            "average_overall_occupation": consolidated["average_overall_occupation"],
            "total_power_consumption": consolidated["total_power_consumption"],
            "active_servers_average": consolidated.get("active_servers_average", 0),
            "active_switches_average": consolidated.get("active_switches_average", 0),
        }
    }
    
    # Gerar nome do arquivo
    filename = f"{output_dir}/metrics.json"
    if run_id is not None:
        filename = f"{output_dir}/metrics_run_{run_id}.json"
        
    with open(filename, "w") as f:
        json.dump(all_metrics, f, indent=4)
        
    print(f"[METRICS] Métricas salvas em: {filename}")
    print(f"[METRICS] Precision: {prediction_metrics['precision']:.2f}% (TP={tp}, FP={fp})")
    print(f"[METRICS] Recall: {prediction_metrics['recall']:.2f}% (TP={tp}, FN={fn})")