"""Tests for Sensor and Actor instances, help texts, and drift detection."""


def test_sensor_instance_generation(generator, temp_workspace):
    target = temp_workspace / "sensor_cfg.yaml"
    success, msg, audit_id = generator.generate_file(
        template_name="sensor_instance",
        target_path=str(target),
        context={
            "instance_name": "temp_probe_bearing_01",
            "sensor_type": "pt1000",
            "unit": "celsius",
            "pin_channel": "SPI_BUS_1",
            "sampling_rate_hz": 250,
            "help_text": "Bearing temperature monitor for high-speed turbine spindle. Alarm at 90C.",
        },
    )
    assert success is True
    content = target.read_text(encoding="utf-8")
    assert "temp_probe_bearing_01" in content
    assert "pt1000" in content
    assert "SPI_BUS_1" in content
    assert "Bearing temperature monitor for high-speed turbine spindle" in content


def test_actor_instance_generation(generator, temp_workspace):
    target = temp_workspace / "actor_cfg.yaml"
    success, msg, audit_id = generator.generate_file(
        template_name="actor_instance",
        target_path=str(target),
        context={
            "instance_name": "main_coolant_valve",
            "actor_type": "proportional_solenoid",
            "control_mode": "pwm_duty",
            "pin_channel": "PWM_CH_4",
            "safety_limit": 98.5,
            "help_text": "Main coolant flow regulation. Failsafe to full open upon signal interruption.",
        },
    )
    assert success is True
    content = target.read_text(encoding="utf-8")
    assert "main_coolant_valve" in content
    assert "proportional_solenoid" in content
    assert "PWM_CH_4" in content
    assert "Failsafe to full open" in content


def test_help_text_drift_detection(comparator):
    original = """# Sensor Instance
instance:
  id: "temp_sensor_01"
  type: "temperature_pt100"
  help_text: "Custom user instructions: Check thermal paste before mounting."
hardware:
  pin_channel: "ADC_CH1"
  sampling_rate_hz: 100
measurement:
  unit: "celsius"
"""
    result = comparator.compare_with_template("sensor_instance", original)
    assert result.drift_detected is True
    assert result.help_text_drift is not None
    assert "Check thermal paste" in result.help_text_drift["client_help_text"]
    assert "Help text drift detected" in result.summary


def test_sensor_migration_retains_help_text_and_calibration(migrator, temp_workspace):
    legacy_file = temp_workspace / "legacy_sensor.yaml"
    legacy_content = """# Legacy sensor configuration
id: "vibration_sensor_gearbox"
type: "accelerometer_triaxial"
pin_channel: "I2C_ADDR_0x68"
sampling_rate_hz: 500
unit: "g"
calibration_offset: -0.05
help_text: "Installed on secondary reduction stage gearbox. Inspect cable integrity every 500 operating hours."
"""
    legacy_file.write_text(legacy_content, encoding="utf-8")

    res = migrator.migrate_file(
        file_path=str(legacy_file),
        template_name="sensor_instance",
        dry_run=False,
    )

    assert res.success is True
    # Retained instance name
    assert res.retained_fields["instance_name"] == "vibration_sensor_gearbox"
    # Retained custom help text!
    assert "Inspect cable integrity every 500 operating hours" in res.retained_help_texts["help_text"]
    assert res.retained_fields["calibration_offset"] == -0.05

    # Check updated file structure
    migrated_text = legacy_file.read_text(encoding="utf-8")
    assert "id: \"vibration_sensor_gearbox\"" in migrated_text
    assert "Inspect cable integrity every 500 operating hours" in migrated_text
    assert "offset: -0.05" in migrated_text
    assert "# Schema Version: 1.0.0" in migrated_text
