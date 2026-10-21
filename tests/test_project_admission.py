"""Current coordinator-owned admission policy for completed real profiles."""

from ibme.assembly import SuiteConfig, list_backends, make_suite, validate_suite


ADMITTED_BACKENDS = {
    "hibe": {
        "latte": {"seed32", "framed32"},
        "lai-ideal-hibe": {"target-research"},
    },
    "ibs": {
        "luo-module": {"research", "c64b"},
        "srgg2025-paper": {"PARAM-I", "PARAM-II", "PARAM-III"},
        "sageloli-rsis": {"PARAM-I", "PARAM-II"},
        "cert-ml-dsa": {"ml-dsa-44", "ml-dsa-65", "ml-dsa-87"},
        "cert-falcon": {"falcon-padded-512", "falcon-padded-1024"},
        "wang-pw-target": {"s0-4"},
    },
}


def _security(config):
    data=config.to_dict()
    return data["security_claim"],data["backend_admitted"],data["parameters_are_formal"]


def test_registry_lists_exact_completed_profile_admissions():
    rows=list_backends()
    for role,expected in ADMITTED_BACKENDS.items():
        actual={row["id"]:set(row["formal_parameter_presets"])
                for row in rows[role] if row["backend_admitted"]}
        assert actual==expected
        for row in rows[role]:
            if row["backend_admitted"]:
                assert row["security_claim"]=="secure"
                assert row["admission_basis"]
            else:
                assert row["security_claim"]=="none"
                assert row["formal_parameter_presets"]==[]


def test_primary_and_completed_showcase_profiles_are_admitted():
    for ibs,preset,fmt in (
        ("cert-ml-dsa","ml-dsa-44","reference"),
        ("cert-falcon","falcon-padded-512","reference"),
        ("luo-module","research","compact"),
        ("luo-module","c64b","compact"),
        ("srgg2025-paper","PARAM-I","compact"),
        ("sageloli-rsis","PARAM-I","reference"),
        ("wang-pw-target","s0-4","reference"),
    ):
        config=make_suite(hibe="latte",hibe_params="seed32",ibs=ibs,ibs_params=preset,
                          transport="hybrid",signature_format=fmt)
        assert _security(config)==("secure",True,True)


def test_selected_cli_state_metadata_copies_suite_admission():
    from ibme import cli

    config=make_suite(hibe="latte",hibe_params="seed32",ibs="cert-ml-dsa",
                      ibs_params="ml-dsa-44",transport="hybrid")
    report=validate_suite(config)
    metadata=cli._selected_metadata(config,report,"0"*64)
    assert (metadata["security_claim"],metadata["backend_admitted"],
            metadata["parameters_are_formal"]) == ("secure",True,True)
    assert all(metadata[name] == config.to_dict()[name] for name in (
        "security_claim","backend_admitted","parameters_are_formal"))


def test_lai_target_is_admitted_but_research_a_point_is_not_promoted():
    target=make_suite(hibe="lai-ideal-hibe",hibe_params="target-research",
                      ibs="cert-ml-dsa",ibs_params="ml-dsa-44",transport="hybrid")
    small=make_suite(hibe="lai-ideal-hibe",hibe_params="hybrid-research",
                     ibs="cert-ml-dsa",ibs_params="ml-dsa-44",transport="hybrid")
    assert _security(target)==("secure",True,True)
    assert _security(small)==("none",False,False)


def test_debug_mock_and_known_negative_controls_remain_unadmitted():
    for options in (
        dict(hibe="mock",ibs="mock",allow_mock=True),
        dict(hibe="abb10",ibs="sis"),
        dict(hibe="chkp",ibs="cert-ml-dsa",transport="hybrid"),
        dict(hibe="latte",hibe_params="seed32",ibs="sageloli-rsis",
             ibs_params="debug-small",transport="hybrid"),
        dict(hibe="latte",hibe_params="seed32",ibs="wang-pw",transport="hybrid"),
        dict(hibe="latte",hibe_params="seed32",ibs="wang-pw-target",
             ibs_params="debug-small",transport="hybrid"),
    ):
        assert _security(make_suite(**options))==("none",False,False)


def test_unadmitted_profile_cannot_forge_project_admission():
    config=make_suite(hibe="abb10",ibs="sis")
    promoted=SuiteConfig.from_dict({**config.to_dict(),
        "security_claim":"secure","backend_admitted":True,
        "parameters_are_formal":True})
    report=validate_suite(promoted)
    assert not report.ok
    assert "admission metadata" in " ".join(report.errors)


def test_luo_matrix_functional_preset_remains_a_known_unsafe_parameter_exception():
    config=make_suite(hibe="latte",hibe_params="seed32",ibs="luo-matrix",
                      ibs_params="research",transport="hybrid")
    params=config.to_dict()["ibs_params"]
    assert (params["n"],params["m"],params["eta"],params["q"])==(4,8,1,2**31-1)
    assert _security(config)==("none",False,False)
    promoted=SuiteConfig.from_dict({**config.to_dict(),"security_claim":"secure",
                                    "backend_admitted":True,"parameters_are_formal":True})
    assert "admission metadata" in " ".join(validate_suite(promoted).errors)


def test_legacy_main_suite_snapshot_remains_loadable_without_rewriting_history():
    current=make_suite(hibe="latte",hibe_params="seed32",ibs="cert-ml-dsa",
                       ibs_params="ml-dsa-44",transport="hybrid")
    values=current.to_dict()
    values["ibs_params"].update(security_claim="none",backend_admitted=False,
                                parameters_are_formal=False)
    legacy=SuiteConfig.from_dict({**values,"security_claim":"none",
                                  "backend_admitted":False,"parameters_are_formal":False})
    assert _security(legacy)==("none",False,False)
    assert "admission metadata" not in " ".join(validate_suite(legacy).errors)
