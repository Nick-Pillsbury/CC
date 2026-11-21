# CC — System Setup Documentation

This document covers the software and network setup that turns the assembled car into something you can drive from anywhere. It walks through installing Raspberry Pi OS on the Pi 5, enabling I2C, connecting the Pi to the Solis Tag cellular hotspot, and installing WireGuard. It then explains how the WireGuard VPS ties the car and the operator together.

For the hardware build (parts, wiring, power), see the [Physical Build Documentation](../Physical_Build_Info/readme.md). For the project overview, see the [Project Proposal](../CC_Proposal.pdf).

---

## Table of Contents

1. [Network Overview](#1-network-overview)
2. [Raspberry Pi Setup](#2-raspberry-pi-setup)
   - [2.1 Install Raspberry Pi OS](#21-install-raspberry-pi-os)
   - [2.2 First Boot](#22-first-boot)
   - [2.3 Enable I2C](#23-enable-i2c)
   - [2.4 Install WireGuard](#24-install-wireguard)
3. [Solis Tag Setup](#3-solis-tag-setup)
4. [WireGuard VPS](#4-wireguard-vps)
   - [4.1 Why a VPS Is Needed](#41-why-a-vps-is-needed)
   - [4.2 How It Connects](#42-how-it-connects)
   - [4.3 Peers Explained](#43-peers-explained)
5. [Verification Checklist](#5-verification-checklist)
6. [Troubleshooting](#6-troubleshooting)
7. [Open Items](#7-open-items)

---

## 1. Network Overview

| Device | Hostname | Role | Internet Connection | Tunnel IP |
|:--|:--|:--|:--|:-:|
| WireGuard VPS | `pivpn` | Hub. The only machine with a public IP; relays traffic between peers | Datacenter, public static IP | `10.0.0.1` |
| Raspberry Pi 5 (car) | `cc` | Peer. Runs the hardware, video, and API containers | Solis Tag cellular hotspot (Wi-Fi) | `10.0.0.<car>` |
| Operator computer | — | Peer. Runs the controller relay and receives the video feed | Any internet (home, campus, phone) | `10.0.0.<operator>` |

The tunnel subnet is **`10.0.0.0/24`** and WireGuard listens on **UDP 51820** on the VPS. `<car>` and `<operator>` stand for each device's assigned address (see [Open Items](#7-open-items)).

---

## 2. Raspberry Pi Setup

### 2.1 Install Raspberry Pi OS

The car runs **Raspberry Pi OS (64-bit)**, based on **Debian 13 "trixie"**. The Lite (headless) image is recommended: the car has no display, and skipping the desktop leaves more CPU and RAM for video encoding.

**You need:** a microSD card (32 GB+, A2 / U3 recommended), a computer with a card reader, and [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

1. Open Raspberry Pi Imager.
2. **Device:** Raspberry Pi 5.
3. **Operating System:** *Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)*.
4. **Storage:** select the microSD card.
5. Click **Next → Edit Settings** and pre-configure the following:

   | Tab | Setting | Value |
   |:--|:--|:--|
   | General | Hostname | `cc` |
   | General | Username / password | Your admin user |
   | General | Wireless LAN | Solis Tag SSID and password (see [§3](#3-solis-tag-setup)). Optionally use your home Wi-Fi for first boot |
   | General | Wireless LAN country | `US` |
   | General | Locale | Your time zone |
   | Services | Enable SSH | ✅ Use public-key authentication (recommended) |

6. Write the card, insert it into the Pi, and power on from the power bank.

### 2.2 First Boot

SSH in using the wireguard peer ip:

```bash
ssh <user>@10.0.0.<car>
```

Update everything and install the basics:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl i2c-tools v4l-utils
sudo reboot
```

Confirm the OS version:

```bash
lsb_release -a
```

![lsb_release output showing Debian GNU/Linux 13 (trixie)](photos/lsb_release.png)

> "No LSB modules are available" is a harmless message on Raspberry Pi OS and can be ignored.

### 2.3 Enable I2C

The Pi talks to the PCA9685 PWM board over I2C bus 1 (header pins 3 / 5). On Raspberry Pi OS this is a single `raspi-config` setting.

**1. Turn on I2C.** Either use the menu:

```bash
sudo raspi-config
# Interface Options → I2C → Yes → Finish
```

or do it in one command:

```bash
sudo raspi-config nonint do_i2c 0     # 0 = enable
```

Both add `dtparam=i2c_arm=on` to `/boot/firmware/config.txt`. Reboot:

```bash
sudo reboot
```

