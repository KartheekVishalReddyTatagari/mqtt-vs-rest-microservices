# Results summary (135 runs)

## Steady state (E1, E2, E5): means over repetitions

Latency in ms; CPU in % of one core and memory in MiB, summed over Processing, Alert and (MQTT) broker. Runs are grouped by experiment, so QoS 1 in E1 and in E5 are separate rows.

| experiment | profile | rate | netem | n | p50 | p95 | p99 | delivered | rate_ok | missed | cpu | mem |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | mqtt-q1 | 10 | none | 3 | 1.29 | 2.43 | 2.82 | 100.00% | 10.0 | 0.0 | 16.5 | 54.1 |
| E1 | rest | 10 | none | 3 | 1.38 | 2.33 | 2.62 | 100.00% | 10.0 | 0.0 | 15.7 | 88.7 |
| E1 | mqtt-q1 | 100 | none | 3 | 0.95 | 1.83 | 2.11 | 100.00% | 100.0 | 0.0 | 25.8 | 55.0 |
| E1 | rest | 100 | none | 3 | 1.05 | 1.54 | 1.77 | 100.00% | 100.0 | 0.0 | 25.6 | 97.4 |
| E1 | mqtt-q1 | 500 | none | 3 | 0.51 | 0.98 | 1.21 | 100.00% | 500.0 | 3.7 | 45.4 | 57.7 |
| E1 | rest | 500 | none | 3 | 0.52 | 0.77 | 0.92 | 100.00% | 500.0 | 1.0 | 46.0 | 91.1 |
| E1 | mqtt-q1 | 1000 | none | 3 | 0.52 | 0.76 | 0.99 | 100.00% | 1,000.0 | 0.0 | 57.9 | 59.0 |
| E1 | rest | 1000 | none | 3 | 0.46 | 0.62 | 0.83 | 100.00% | 1,000.0 | 3.0 | 61.4 | 93.3 |
| E2 | mqtt-q1 | 100 | delay100 | 3 | 411.27 | 430.01 | 441.28 | 100.00% | 100.0 | 0.3 | 21.7 | 55.2 |
| E2 | rest | 100 | delay100 | 3 | 201.06 | 214.81 | 218.38 | 100.00% | 100.0 | 0.7 | 25.5 | 91.4 |
| E2 | mqtt-q1 | 100 | delay50 | 3 | 202.59 | 211.59 | 215.01 | 100.00% | 100.0 | 0.0 | 23.8 | 55.4 |
| E2 | rest | 100 | delay50 | 3 | 101.06 | 107.97 | 109.77 | 100.00% | 100.0 | 0.0 | 24.8 | 89.9 |
| E2 | mqtt-q1 | 100 | delay50-loss1 | 3 | 270.44 | 393.90 | 463.24 | 100.00% | 100.0 | 0.7 | 20.8 | 55.1 |
| E2 | rest | 100 | delay50-loss1 | 3 | 101.22 | 108.66 | 421.16 | 100.00% | 100.0 | 0.3 | 25.3 | 90.1 |
| E2 | mqtt-q1 | 100 | loss1 | 3 | 0.98 | 7.21 | 44.91 | 100.00% | 100.0 | 1.0 | 25.6 | 54.7 |
| E2 | rest | 100 | loss1 | 3 | 1.08 | 1.84 | 207.56 | 100.00% | 100.0 | 0.0 | 26.5 | 88.9 |
| E2 | mqtt-q1 | 100 | loss5 | 3 | 1.47 | 205.23 | 416.81 | 100.00% | 100.0 | 0.0 | 23.7 | 54.8 |
| E2 | rest | 100 | loss5 | 3 | 1.08 | 209.85 | 273.13 | 100.00% | 100.0 | 0.0 | 26.0 | 89.3 |
| E5 | mqtt-q0 | 100 | loss1 | 3 | 1.08 | 11.03 | 73.59 | 100.00% | 100.0 | 0.0 | 22.1 | 54.4 |
| E5 | mqtt-q2 | 100 | loss1 | 3 | 2.13 | 13.43 | 147.76 | 100.00% | 100.0 | 0.0 | 31.1 | 54.7 |
| E5 | mqtt-q0 | 1000 | loss1 | 3 | 0.58 | 134.11 | 222.96 | 100.00% | 1,000.0 | 5.0 | 48.2 | 57.8 |
| E5 | mqtt-q1 | 1000 | loss1 | 3 | 0.59 | 124.75 | 204.35 | 100.00% | 1,000.0 | 2.3 | 56.4 | 58.9 |
| E5 | mqtt-q2 | 1000 | loss1 | 3 | 1.07 | 206.11 | 365.01 | 100.00% | 1,000.0 | 1.3 | 63.7 | 59.7 |
| E5 | mqtt-q0 | 100 | none | 3 | 1.00 | 1.40 | 1.62 | 100.00% | 100.0 | 0.0 | 22.0 | 54.9 |
| E5 | mqtt-q2 | 100 | none | 3 | 1.77 | 2.98 | 3.47 | 100.00% | 100.0 | 0.0 | 30.5 | 54.6 |
| E5 | mqtt-q0 | 1000 | none | 3 | 0.54 | 0.85 | 1.02 | 100.00% | 1,000.0 | 2.7 | 49.6 | 58.1 |
| E5 | mqtt-q2 | 1000 | none | 3 | 0.89 | 1.21 | 1.53 | 100.00% | 1,000.0 | 8.7 | 72.6 | 59.2 |

## REST (a) vs MQTT QoS 1 (b), run-level statistics

Cliff's delta: +1 = every MQTT run higher than every REST run, -1 = every one lower. n = 3 to 3 runs per group; the smallest p a Mann-Whitney test can give is 0.1 at n = 3.

| experiment | rate | netem | metric | n_a | n_b | mean_a | mean_b | ratio_b_over_a | welch_p | mannwhitney_p | cliffs_delta |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | 10 | none | lat_p50_ms | 3 | 3 | 1.38 | 1.29 | 0.94 | 0.566 | 0.700 | -0.333 |
| E1 | 10 | none | lat_p99_ms | 3 | 3 | 2.62 | 2.82 | 1.08 | 0.797 | 0.400 | 0.556 |
| E1 | 10 | none | cpu_system_pct | 3 | 3 | 15.71 | 16.51 | 1.05 | 0.033 | 0.100 | 1.000 |
| E1 | 10 | none | mem_system_mib | 3 | 3 | 88.69 | 54.06 | 0.61 | 0.000 | 0.100 | -1.000 |
| E1 | 100 | none | lat_p50_ms | 3 | 3 | 1.05 | 0.95 | 0.91 | 0.455 | 0.400 | -0.556 |
| E1 | 100 | none | lat_p99_ms | 3 | 3 | 1.77 | 2.11 | 1.20 | 0.409 | 0.700 | 0.333 |
| E1 | 100 | none | cpu_system_pct | 3 | 3 | 25.62 | 25.85 | 1.01 | 0.820 | 1.000 | 0.111 |
| E1 | 100 | none | mem_system_mib | 3 | 3 | 97.44 | 54.99 | 0.56 | 0.040 | 0.100 | -1.000 |
| E1 | 500 | none | lat_p50_ms | 3 | 3 | 0.52 | 0.51 | 0.99 | 0.900 | 0.658 | -0.333 |
| E1 | 500 | none | lat_p99_ms | 3 | 3 | 0.92 | 1.21 | 1.32 | 0.145 | 0.100 | 1.000 |
| E1 | 500 | none | cpu_system_pct | 3 | 3 | 45.95 | 45.38 | 0.99 | 0.767 | 0.700 | -0.333 |
| E1 | 500 | none | mem_system_mib | 3 | 3 | 91.06 | 57.67 | 0.63 | 0.000 | 0.100 | -1.000 |
| E1 | 1000 | none | lat_p50_ms | 3 | 3 | 0.46 | 0.52 | 1.11 | 0.146 | 0.100 | 1.000 |
| E1 | 1000 | none | lat_p99_ms | 3 | 3 | 0.83 | 0.99 | 1.20 | 0.030 | 0.100 | 1.000 |
| E1 | 1000 | none | cpu_system_pct | 3 | 3 | 61.39 | 57.85 | 0.94 | 0.001 | 0.100 | -1.000 |
| E1 | 1000 | none | mem_system_mib | 3 | 3 | 93.26 | 58.98 | 0.63 | 0.000 | 0.100 | -1.000 |
| E2 | 100 | delay100 | lat_p50_ms | 3 | 3 | 201.06 | 411.27 | 2.05 | 0.000 | 0.100 | 1.000 |
| E2 | 100 | delay100 | lat_p99_ms | 3 | 3 | 218.38 | 441.28 | 2.02 | 0.000 | 0.100 | 1.000 |
| E2 | 100 | delay100 | cpu_system_pct | 3 | 3 | 25.51 | 21.67 | 0.85 | 0.042 | 0.100 | -1.000 |
| E2 | 100 | delay100 | mem_system_mib | 3 | 3 | 91.40 | 55.19 | 0.60 | 0.000 | 0.100 | -1.000 |
| E2 | 100 | delay50 | lat_p50_ms | 3 | 3 | 101.06 | 202.59 | 2.00 | 0.000 | 0.100 | 1.000 |
| E2 | 100 | delay50 | lat_p99_ms | 3 | 3 | 109.77 | 215.01 | 1.96 | 0.000 | 0.100 | 1.000 |
| E2 | 100 | delay50 | cpu_system_pct | 3 | 3 | 24.83 | 23.78 | 0.96 | 0.120 | 0.100 | -1.000 |
| E2 | 100 | delay50 | mem_system_mib | 3 | 3 | 89.95 | 55.45 | 0.62 | 0.000 | 0.100 | -1.000 |
| E2 | 100 | delay50-loss1 | lat_p50_ms | 3 | 3 | 101.22 | 270.44 | 2.67 | 0.000 | 0.100 | 1.000 |
| E2 | 100 | delay50-loss1 | lat_p99_ms | 3 | 3 | 421.16 | 463.24 | 1.10 | 0.229 | 0.100 | 1.000 |
| E2 | 100 | delay50-loss1 | cpu_system_pct | 3 | 3 | 25.28 | 20.83 | 0.82 | 0.003 | 0.100 | -1.000 |
| E2 | 100 | delay50-loss1 | mem_system_mib | 3 | 3 | 90.08 | 55.10 | 0.61 | 0.000 | 0.100 | -1.000 |
| E2 | 100 | loss1 | lat_p50_ms | 3 | 3 | 1.08 | 0.98 | 0.91 | 0.329 | 0.400 | -0.556 |
| E2 | 100 | loss1 | lat_p99_ms | 3 | 3 | 207.56 | 44.91 | 0.22 | 0.019 | 0.100 | -1.000 |
| E2 | 100 | loss1 | cpu_system_pct | 3 | 3 | 26.47 | 25.61 | 0.97 | 0.429 | 0.400 | -0.556 |
| E2 | 100 | loss1 | mem_system_mib | 3 | 3 | 88.94 | 54.66 | 0.61 | 0.000 | 0.100 | -1.000 |
| E2 | 100 | loss5 | lat_p50_ms | 3 | 3 | 1.08 | 1.47 | 1.35 | 0.014 | 0.100 | 1.000 |
| E2 | 100 | loss5 | lat_p99_ms | 3 | 3 | 273.13 | 416.81 | 1.53 | 0.175 | 0.100 | 1.000 |
| E2 | 100 | loss5 | cpu_system_pct | 3 | 3 | 26.03 | 23.67 | 0.91 | 0.076 | 0.100 | -1.000 |
| E2 | 100 | loss5 | mem_system_mib | 3 | 3 | 89.31 | 54.76 | 0.61 | 0.000 | 0.100 | -1.000 |

## Outages (E3): means over repetitions

sent_late = readings the producer could not send within 10 ms of their due time; recovery and drain are measured from the restart command; max_age = oldest reading due during the outage, from its due time to its arrival.

| fault_target | outage_s | profile | delivered | lost | duplicates | sent_late | lag_p99_ms | recovery_s | drain_s | max_age_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| alert | 10.0 | mqtt-q0 | 82.8% | 2,068.7 | 0.0 | 0.7 | 1.1 | 0.6 | 0.6 | 4.0 |
| alert | 10.0 | mqtt-q1 | 100.0% | 0.0 | 0.0 | 0.3 | 0.9 | 0.6 | 0.6 | 10,097.7 |
| alert | 10.0 | rest | 94.9% | 609.7 | 0.0 | 1,698.7 | 5,607.4 | 2.7 | 3.7 | 10,494.4 |
| alert | 10.0 | rest-retry | 100.0% | 0.0 | 0.0 | 1,792.7 | 8,000.3 | 3.3 | 4.1 | 13,708.4 |
| alert | 30.0 | mqtt-q0 | 62.1% | 6,068.0 | 0.0 | 0.7 | 1.0 | 0.6 | 0.6 | 2.1 |
| alert | 30.0 | mqtt-q1 | 100.0% | 0.0 | 0.0 | 0.0 | 1.4 | 0.6 | 0.8 | 30,102.4 |
| alert | 30.0 | rest | 90.0% | 1,606.7 | 0.0 | 5,687.0 | 19,687.1 | 2.0 | 3.7 | 24,773.3 |
| alert | 30.0 | rest-retry | 100.0% | 0.0 | 351.0 | 5,867.0 | 27,213.2 | 2.7 | 4.5 | 32,871.3 |
| processing | 10.0 | mqtt-q0 | 82.8% | 2,069.7 | 0.0 | 0.3 | 1.2 | 0.6 | 0.6 | 2.1 |
| processing | 10.0 | mqtt-q1 | 100.0% | 0.0 | 0.0 | 0.7 | 1.0 | 0.6 | 0.6 | 10,104.3 |
| processing | 10.0 | rest | 99.9% | 7.7 | 0.0 | 1,328.0 | 5,775.8 | 0.7 | 2.5 | 11,583.8 |
| processing | 10.0 | rest-retry | 100.0% | 0.0 | 0.0 | 1,316.0 | 5,739.1 | 0.7 | 2.4 | 11,487.5 |
| processing | 30.0 | mqtt-q0 | 62.0% | 6,072.0 | 0.0 | 3.7 | 1.2 | 0.6 | 0.6 | 1.4 |
| processing | 30.0 | mqtt-q1 | 100.0% | 0.0 | 0.0 | 7.0 | 1.2 | 0.9 | 1.4 | 30,562.5 |
| processing | 30.0 | rest | 91.7% | 1,322.7 | 0.0 | 5,343.0 | 24,873.0 | 0.7 | 2.0 | 24,666.1 |
| processing | 30.0 | rest-retry | 100.0% | 1.3 | 10.3 | 5,403.3 | 25,068.6 | 0.7 | 2.3 | 31,282.5 |

## Broker outage (E6, MQTT QoS 1)

| outage_s | fault_mode | n | delivered | lost | duplicates | sent_late | lag_p99_ms | recovery_s | drain_s | max_age_ms | unavailable_s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10.0 | abrupt | 3 | 100.00% | 0.0 | 1.3 | 1,616.7 | 7,349.1 | 2.6 | 3.2 | 12,673.8 | 10.2 |
| 10.0 | graceful | 3 | 100.00% | 0.0 | 1.0 | 1,615.7 | 7,348.8 | 2.6 | 3.2 | 12,627.8 | 10.2 |

## Figures

- fig1_latency_vs_rate.png
- fig2_latency_cdf.png
- fig3_network_conditions.png
- fig4_outage_delivery.png
- fig6_cpu.png
- fig7_memory.png
- fig8_qos_tradeoff.png
- fig5_timeline_alert_10s.png
- fig5_timeline_alert_30s.png
- fig5_timeline_processing_10s.png
- fig5_timeline_processing_30s.png
- fig9_broker_outage_10s.png
