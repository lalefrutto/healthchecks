# locust-k8s-operator

Оператор для распределённого Locust в кластере (Задание 7, Часть 4).

```sh
helm repo add locust-k8s-operator https://abdelrhmanhamouda.github.io/locust-k8s-operator/
helm upgrade --install locust-operator locust-k8s-operator/locust-k8s-operator \
  -n locust-operator --create-namespace
```

Оператор следит за CR `LocustTest` (`locust.io/v2`) и на каждый создаёт Job'ы
`<name>-master` и `<name>-worker` (N реплик) и Service `<name>-master`
(5557/5558 для воркеров, 9646 — Prometheus-метрики). Сам тест описан
чартом [charts/locust-test](../../charts/locust-test/README.md).
