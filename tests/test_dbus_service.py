from homewizard.dbus_service import publish, text_for


def test_publish_online():
    svc = {"/UpdateIndex": 255}
    publish(svc, ["/Ac/Power"], {"/Ac/Power": 1200})
    assert svc == {"/Ac/Power": 1200, "/Connected": 1, "/UpdateIndex": 0}


def test_publish_offline_clears_paths():
    svc = {"/UpdateIndex": 3, "/Ac/Power": 1200}
    publish(svc, ["/Ac/Power"], None)
    assert svc["/Ac/Power"] is None and svc["/Connected"] == 0 and svc["/UpdateIndex"] == 4


def test_text_for():
    assert text_for("/Ac/L1/Power")("/Ac/L1/Power", 1234.4) == "1234W"
    assert text_for("/Ac/Energy/Forward")("", 1.234) == "1.23kWh"
    assert text_for("/Ac/Power")("", None) == "---"
