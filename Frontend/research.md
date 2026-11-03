# Interface Development Log

## Overview
Initial commit establishing the multi-layer display canvas and Chromium renderer.

## Changes & Implementation
* Configured `QStackedLayout` using `StackingMode.StackAll` to place an overlay canvas directly over the embedded web view.
* Implemented `StreamWebPage` inheriting from `QWebEnginePage` with `certificateError()` returning `True` to bypass local self-signed SSL validation for LAN stream sources.
* Passed `--ignore-certificate-errors` and `--allow-running-insecure-content` flags into `sys.argv` before `QApplication` instantiation to silence Chromium security warnings.

## Edge Cases & Limitations
* **Mouse Event Occlusion**: The upper `self.overlay_widget` plane captures all mouse interactions by default, preventing clicks, drags, or context menu access on the underlying stream web page.
* **Certificate Signature Variations**: Modern PyQt6 bindings may pass a `QWebEngineCertificateError` object into `certificateError()` instead of an error code, which can produce warnings in strict type-checked runtimes.
* **Autoplay Blocking**: Feeds with audio tracks may fail to start playing immediately without user interaction due to Chromium's default autoplay security model.
