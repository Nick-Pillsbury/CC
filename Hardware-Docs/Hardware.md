# Cellular Car (CC) — Physical Components Documentation

## System Architecture

```
[Operator Cockpit]
 ├── Input: Xbox Wireless Controller
 └── Visual Sink: Meta Quest Headset (HDMI Passthrough)
       │
       ▼ (Cellular Network: 4G LTE / 5G)
       │
[Vehicle Compute & Actuation Platform]
 ├── Compute Host: Raspberry Pi (Model: [TODO])
 ├── PWM Coprocessor: HiLetgo PCA9685 (I2C: 0x40)
 ├── Inverter: GoolRC 45A Brushless ESC
 ├── Drivetrain: DEERC 1:10 4WD Brushless RC Car
 └── Steering: DEERC 3-Wire Servo
```

---

## BOM

### Chassis & Drivetrain
* DEERC 1:10 Fast Brushless 4WD RC Car
* Vehicle frame, suspension, steering linkage, and mechanical drive.
* [Amazon / DEERC Store](https://www.amazon.com/s?k=DEERC+1%3A10+brushless+rc+car)

### Electronic Speed Controller (ESC)
* GoolRC Waterproof 45A Brushless ESC
* Motor driver and onboard 5.8V / 3A BEC power supply for steering.
* [Amazon](https://www.amazon.com/s?k=GoolRC+Waterproof+45A+Brushless+ESC)

### PWM Motor Driver
* HiLetgo PCA9685 16-Channel 12-Bit PWM Driver
* Dedicated hardware servo and ESC signal generator over I2C.
* [Amazon](https://www.amazon.com/HiLetgo-PCA9685-Channel-12-Bit-Arduino/dp/B07BRS249H)

# Raspberry Pi 
* Cellular socket communication, camera capture, and I2C command control.


### Pi Power Supply
* USB-C Portable Power Bank
* Dedicated 5V supply for Raspberry Pi.

### Motor Power Supply
* Car LiPo/Li-ion Battery Pack
* 7.4V – 11.1V high-current supply for ESC and drivetrain motor.

### Cellular Interface
*  Cellular Modem / Dongle
* Network backhaul interface.
* **Status:** `[TODO: Specify USB dongle or HAT]`

### Camera 
* Video Camera
* Real-time visual telemetry to Meta Quest.
* **Status:** `[TODO: Specify CSI ribbon camera or USB webcam]`

### Meta Quest Ingest Bridge
* HDMI-to-USB-C UVC Video Capture Card
* Video input adapter for Meta Quest passthrough.
* **Status:** `[TODO:]`

---

## Interconnect & Pin Mapping

### Logic & Signal Connections

| Source | Source Pin / Port | Destination | Destination Pin / Port | Signal Type | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Raspberry Pi | Pin 1 (3.3V) | PCA9685 | VCC | 3.3V Power | Chip logic supply |
| Raspberry Pi | Pin 3 (GPIO 2) | PCA9685 | SDA | I2C Data | Default address `0x40` |
| Raspberry Pi | Pin 5 (GPIO 3) | PCA9685 | SCL | I2C Clock | Default address `0x40` |
| Raspberry Pi | Pin 9 (GND) | PCA9685 | GND | Ground | Common reference |
| PCA9685 | Ch 0 Signal | GoolRC ESC | White / Orange Wire | 50 Hz PWM | Throttle output |
| PCA9685 | Ch 1 Signal | DEERC Servo | White / Orange Wire | 50 Hz PWM | Steering output |

### Power Distribution

| Power Source | Output Rating | Destination | Destination Terminal | Notes |
| :--- | :--- | :--- | :--- | :--- |
| USB-C Power Bank | 5V / 3A (min) | Raspberry Pi | USB-C Power Port | Isolated from drive electronics |
| Car Battery Pack | 7.4V – 11.1V | GoolRC ESC | Main T/XT60 Leads | Supplies motor traction power |
| GoolRC ESC (BEC) | ~5.8V / 3A | PCA9685 | $V+$ Screw Terminal | Supplies servo power rail |
| GoolRC ESC (BEC) | 0V | PCA9685 | GND Screw Terminal | Common ground tie |

---

## General Usage and Safety
* Runaway Prevention: Software must implement a watchdog timer that cuts throttle to neutral if cellular telemetry drops for >500 ms.

* LiPo Battery Care: Disconnect traction battery immediately after driving; never leave connected in storage to avoid deep discharge.

* Thermal Management: Allow ESC and motor to cool between battery swaps.

* Bench Testing: Always remove wheels or place vehicle on a secure stand whenever testing control loops or network code indoors.