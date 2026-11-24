import pandas as pd
import pytest

from app.services.pipeline_service import PipelineTooLarge, write_processed_frame


def test_output_size_limit_removes_temporary_and_published_files(tmp_path):
    with pytest.raises(PipelineTooLarge):
        write_processed_frame(pd.DataFrame({"value": ["a fairly long output"]}), "csv", tmp_path, "a" * 32, 2)
    processed = tmp_path / "processed"
    assert list(processed.iterdir()) == []
