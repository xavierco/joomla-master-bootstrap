from nokia_compare import (
    build_contextual_lines,
    compare_pair,
    diff_lines,
    extract_block,
    normalize_full_config,
)

SAMPLE_CONFIG_A = """\
configure
    system
        name "080000-RDC01-7s-SANTAFE"
    exit
    router "Base"
        interface "system"
            address 10.0.0.1/32
        exit
        bgp
            group "PEERS"
                peer-as 65000
            exit
        exit
    exit
    policy-options
        prefix-list "CUSTOMERS"
            prefix 192.168.0.0/16 longer
        exit
        policy-statement "EXPORT-BGP"
            entry 10
                from
                    prefix-list "CUSTOMERS"
                exit
                action accept
                exit
            exit
        exit
    exit
exit
"""

SAMPLE_CONFIG_B = """\
configure
    system
        name "080000-RDC02-7s-SANTAFE"
    exit
    router "Base"
        interface "system"
            address 10.0.0.2/32
        exit
        bgp
            group "PEERS"
                peer-as 65001
            exit
        exit
    exit
    policy-options
        prefix-list "CUSTOMERS"
            prefix 192.168.0.0/16 longer
        exit
        policy-statement "EXPORT-BGP"
            entry 10
                from
                    prefix-list "CUSTOMERS"
                exit
                action accept
                exit
            exit
        exit
    exit
exit
"""


def test_extract_block_returns_only_policy_options_contents():
    block = extract_block(SAMPLE_CONFIG_A, "policy-options")
    joined = "\n".join(block)
    assert 'prefix-list "CUSTOMERS"' in joined
    assert 'policy-statement "EXPORT-BGP"' in joined
    # No debe incluir nada del bloque 'router' ni 'system'
    assert "bgp" not in joined
    assert "system" not in joined


def test_extract_block_missing_keyword_returns_empty():
    assert extract_block(SAMPLE_CONFIG_A, "qos") == []


def test_normalize_full_config_masks_system_name_and_interface_ip():
    normalized = normalize_full_config(SAMPLE_CONFIG_A)
    joined = "\n".join(normalized)
    assert "<SYSTEM_NAME>" in joined
    assert "080000-RDC01-7s-SANTAFE" not in joined
    assert "<IP>/32" in joined
    assert "10.0.0.1" not in joined


def test_build_contextual_lines_tracks_hierarchy():
    lines = extract_block(SAMPLE_CONFIG_A, "policy-options")
    contextual = build_contextual_lines(lines)
    # La linea del prefix debe estar dentro del contexto de su prefix-list
    prefix_entry = next(c for c in contextual if c[1].startswith("prefix 192.168"))
    assert 'prefix-list "CUSTOMERS"' in prefix_entry[0]


def test_diff_lines_flags_differences_as_distinto():
    a = build_contextual_lines(["peer-as 65000"])
    b = build_contextual_lines(["peer-as 65001"])
    rows = diff_lines(a, b)
    assert len(rows) == 1
    context, tipo, line_a, line_b = rows[0]
    assert tipo == "Distinto"
    assert line_a == "peer-as 65000"
    assert line_b == "peer-as 65001"


def test_compare_pair_policy_mode_has_no_differences_when_policies_match():
    rows = compare_pair(SAMPLE_CONFIG_A, SAMPLE_CONFIG_B, mode="policy")
    assert rows == []


def test_compare_pair_full_mode_ignores_hostname_and_interface_ip():
    rows = compare_pair(SAMPLE_CONFIG_A, SAMPLE_CONFIG_B, mode="full")
    tipos_y_lineas = [(tipo, line_a, line_b) for _, tipo, line_a, line_b in rows]
    # La unica diferencia real (peer-as) debe aparecer...
    assert ("Distinto", "peer-as 65000", "peer-as 65001") in tipos_y_lineas
    # ...y el hostname / IP normalizados NO deben generar diferencias
    for _, line_a, line_b in tipos_y_lineas:
        assert "080000-RDC01" not in line_a and "080000-RDC02" not in line_b
        assert "10.0.0.1" not in line_a and "10.0.0.2" not in line_b
