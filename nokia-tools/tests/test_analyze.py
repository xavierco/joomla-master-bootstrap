from nokia_tools.analyze import parse_system_information, find_port_issues

SAMPLE_SYSTEM_INFO = """
System Information
-------------------------------------------------------------------------------
System Name            : R1-LAB
System Type            : 7750 SR-7
System Version         : B-21.10.R1
System Up Time         : 12 days, 03:44:10.00 (hr:min:sec)
"""

SAMPLE_PORT_STATE = """
Ports on Slot 1
===============================================================================
Port          Admin  Link    Port          Cfg   Oper  LAG/Bndl
Id            State  State   State         MTU   MTU   Id
-------------------------------------------------------------------------------
1/1/1         Up     Yes     Up            1514  1514
1/1/2         Up     No      Down          1514  1514
"""


def test_parse_system_information():
    parsed = parse_system_information(SAMPLE_SYSTEM_INFO)
    assert parsed["system_name"] == "R1-LAB"
    assert parsed["system_type"] == "7750 SR-7"
    assert parsed["system_version"] == "B-21.10.R1"
    assert parsed["system_up_time"].startswith("12 days")


def test_find_port_issues():
    issues = find_port_issues(SAMPLE_PORT_STATE)
    assert len(issues) == 1
    assert "1/1/2" in issues[0]
