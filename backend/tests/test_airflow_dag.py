import ast
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "airflow" / "dags"))
from dag_factory import DataPulseResponseError, pipeline_id_to_dag_id, read_schedule_manifests, request_datapulse


PIPELINE_ID = "cc50d35e-50b7-4938-9474-d8c3c64f920e"


def manifest():
    return {"pipeline_id": PIPELINE_ID, "dag_id": "datapulse_pipeline_cc50d35e50b749389474d8c3c64f920e",
            "schedule_type": "hourly", "cron_expression": "0 * * * *", "timezone": "UTC",
            "start_date": None, "retries": 2, "retry_delay_seconds": 60, "timeout_seconds": 900}


def test_dag_identity_and_manifest_loading_are_stable_and_ignore_invalid_files(tmp_path):
    item = manifest()
    (tmp_path / f"{item['dag_id']}.json").write_text(__import__("json").dumps(item), encoding="utf-8")
    (tmp_path / "untrusted.json").write_text("{}", encoding="utf-8")
    assert pipeline_id_to_dag_id(PIPELINE_ID) == item["dag_id"]
    assert read_schedule_manifests(tmp_path) == [item]
    assert read_schedule_manifests(tmp_path / "missing") == []


def test_internal_api_request_uses_bearer_token_timeout_and_json(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{"status":"success"}'
    captured = {}
    def open_request(request, timeout):
        captured.update(url=request.full_url, method=request.method, headers=request.headers,
                        body=request.data, timeout=timeout)
        return Response()
    monkeypatch.setattr("dag_factory.urllib.request.urlopen", open_request)
    assert request_datapulse("POST", "/internal/test", {"value": 1}, "http://api:8000/api", "token", 12) == {"status": "success"}
    assert captured["url"] == "http://api:8000/api/internal/test"
    assert captured["method"] == "POST" and captured["timeout"] == 12
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["body"] == b'{"value": 1}'


def test_internal_api_permanent_4xx_is_exposed_as_bounded_safe_error(monkeypatch):
    from urllib.error import HTTPError
    def fail(*_args, **_kwargs):
        raise HTTPError("http://api", 422, "bad request", {}, None)
    monkeypatch.setattr("dag_factory.urllib.request.urlopen", fail)
    with pytest.raises(DataPulseResponseError) as error:
        request_datapulse("GET", "/internal/test", None, "http://api", "token", 2)
    assert error.value.status_code == 422


def test_airflow_dag_file_has_valid_python_syntax():
    dag_file = Path(__file__).parents[2] / "airflow" / "dags" / "datapulse_scheduled_pipelines.py"
    ast.parse(dag_file.read_text(encoding="utf-8"), filename=str(dag_file))


def test_dag_generator_imports_with_mocked_airflow_and_builds_bounded_tasks(tmp_path, monkeypatch):
    item = manifest()
    schedules = tmp_path / "schedules"
    schedules.mkdir()
    (schedules / f"{item['dag_id']}.json").write_text(json.dumps(item), encoding="utf-8")
    monkeypatch.setenv("DATAPULSE_AIRFLOW_SCHEDULES_DIR", str(schedules))

    class FakeDate:
        def in_timezone(self, _timezone): return self
    class FakeDAG:
        instances = []
        def __init__(self, **kwargs): self.kwargs=kwargs;self.instances.append(self)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class FakeOperator:
        instances = []
        def __init__(self, **kwargs): self.kwargs=kwargs;self.instances.append(self)
        def __rshift__(self, other): return other
    class AirflowException(Exception): pass
    class AirflowFailException(AirflowException): pass
    airflow=types.ModuleType("airflow");airflow.DAG=FakeDAG
    exceptions=types.ModuleType("airflow.exceptions");exceptions.AirflowException=AirflowException;exceptions.AirflowFailException=AirflowFailException
    operators=types.ModuleType("airflow.operators");python_operators=types.ModuleType("airflow.operators.python");python_operators.PythonOperator=FakeOperator
    cron=types.ModuleType("croniter");cron.croniter=types.SimpleNamespace(is_valid=lambda _value:True)
    pendulum=types.ModuleType("pendulum");pendulum.timezone=lambda name:name;pendulum.datetime=lambda *_args,**_kwargs:FakeDate();pendulum.parse=lambda _value:FakeDate()
    for name,module in {"airflow":airflow,"airflow.exceptions":exceptions,"airflow.operators":operators,
                        "airflow.operators.python":python_operators,"croniter":cron,"pendulum":pendulum}.items():
        monkeypatch.setitem(sys.modules,name,module)
    dag_file=Path(__file__).parents[2]/"airflow"/"dags"/"datapulse_scheduled_pipelines.py"
    spec=importlib.util.spec_from_file_location("datapulse_scheduled_pipelines_test",dag_file)
    module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,module);spec.loader.exec_module(module)
    dag=module.__dict__[item["dag_id"]]
    assert dag.kwargs["schedule"] == "0 * * * *"
    assert dag.kwargs["catchup"] is False and dag.kwargs["max_active_runs"] == 1
    assert dag.kwargs["default_args"]["retries"] == 2
    assert [task.kwargs["task_id"] for task in FakeOperator.instances] == ["validate_pipeline","execute_pipeline"]
    assert FakeOperator.instances[1].kwargs["execution_timeout"].total_seconds() == 900
    monkeypatch.setattr(module,"request_datapulse",lambda *_args,**_kwargs: (_ for _ in ()).throw(DataPulseResponseError(422,"invalid selection")))
    with pytest.raises(AirflowFailException):
        module._call("POST","/invalid",{})
    monkeypatch.setattr(module,"request_datapulse",lambda *_args,**_kwargs: (_ for _ in ()).throw(DataPulseResponseError(503,"temporarily unavailable")))
    with pytest.raises(AirflowException) as error:
        module._call("POST","/temporary",{})
    assert not isinstance(error.value,AirflowFailException)
