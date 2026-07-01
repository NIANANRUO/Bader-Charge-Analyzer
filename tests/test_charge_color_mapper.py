from rendering.charge_color_mapper import ChargeColorMapper


def test_positive_charge_maps_red_and_labels_electron_gain():
    mapper = ChargeColorMapper([-1.0, 0.0, 1.0])

    red, _, blue = mapper.rgb_for_charge(0.5)

    assert red > blue
    assert mapper.label_for_charge(0.5) == "electron gain"


def test_negative_charge_maps_blue_and_labels_electron_loss():
    mapper = ChargeColorMapper([-1.0, 0.0, 1.0])

    red, _, blue = mapper.rgb_for_charge(-0.5)

    assert blue > red
    assert mapper.label_for_charge(-0.5) == "electron loss"


def test_zero_charge_is_neutral_gray_and_clim_is_symmetric():
    mapper = ChargeColorMapper([-2.0, 0.0, 1.0])

    assert mapper.rgb_for_charge(0.0) == (0.85, 0.85, 0.85)
    assert mapper.label_for_charge(0.0) == "neutral"
    assert mapper.clim == (-2.0, 2.0)


def test_empty_charges_use_default_symmetric_clim():
    mapper = ChargeColorMapper([])

    assert mapper.clim == (-1.0, 1.0)


def test_all_zero_charges_use_default_symmetric_clim():
    mapper = ChargeColorMapper([0.0, 0.0])

    assert mapper.clim == (-1.0, 1.0)


def test_non_finite_charges_are_ignored_for_clim_and_mapped_as_neutral():
    mapper = ChargeColorMapper([float("nan"), float("inf"), -float("inf"), 0.25])

    assert mapper.clim == (-0.25, 0.25)
    assert mapper.rgb_for_charge(float("nan")) == (0.85, 0.85, 0.85)
    assert mapper.label_for_charge(float("nan")) == "neutral"
