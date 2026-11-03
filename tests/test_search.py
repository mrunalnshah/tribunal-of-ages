from tribunal.search import container_cpus


def test_a_container_quota_sets_the_thread_count(tmp_path):
    (tmp_path / "cpu.max").write_text("200000 100000\n")  # a quota of 2 CPUs
    assert container_cpus(tmp_path) == 2


def test_no_quota_means_every_core(tmp_path):
    (tmp_path / "cpu.max").write_text("max 100000\n")
    assert container_cpus(tmp_path) is None
    assert container_cpus(tmp_path / "missing") is None  # not in a container at all


def test_older_hosts_use_cgroup_v1(tmp_path):
    (tmp_path / "cpu").mkdir()
    (tmp_path / "cpu" / "cpu.cfs_quota_us").write_text("100000\n")
    (tmp_path / "cpu" / "cpu.cfs_period_us").write_text("100000\n")
    assert container_cpus(tmp_path) == 1
    (tmp_path / "cpu" / "cpu.cfs_quota_us").write_text("-1\n")  # v1's "no quota"
    assert container_cpus(tmp_path) is None
