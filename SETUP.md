# Setup & Deployment Guide

This guide walks you through deploying **cursed-resonance** as a serverless endpoint on RunPod, connected dynamically to your Cloudflare R2 bucket.

## 1. Prerequisites
- A **RunPod** account.
- A **Cloudflare R2** account (with a bucket containing your `controlfoley` and `ace-step` models).
- A **GitHub** account to host this repository and build the Docker image.

## 2. Pushing to GitHub (GHCR)
1. Create a repository on GitHub (e.g., `cursed-resonance`) and push this code.
2. Add a GitHub Action workflow to automatically build the Docker image and push it to GHCR.
3. Your final image URL will look like: `ghcr.io/your-username/cursed-resonance:latest`

## 3. Configuring Cloudflare R2
For the `handler.py` to dynamically pull your heavy audio models without embedding them in the Docker image, you need your R2 credentials.

Go to your Cloudflare R2 Dashboard and generate an API token with **Object Read/Write** permissions. Note down the:
- Account ID
- Access Key ID
- Secret Access Key

## 4. Deploying to RunPod Serverless
1. Go to the **RunPod Serverless** dashboard.
2. Click **New Endpoint**.
3. Under **Template**, select or create a template that uses your GHCR image URL: `ghcr.io/your-username/cursed-resonance:latest`.
4. Set your Container Disk and Volume Disk (around 20GB).
5. **CRITICAL:** Scroll down to **Environment Variables** and add the following keys:
   - `R2_ACCOUNT_ID` = `(Your 32-character Account ID)`
   - `R2_ACCESS_KEY_ID` = `(Your R2 Access Key)`
   - `R2_SECRET_ACCESS_KEY` = `(Your R2 Secret Key)`
   - `R2_BUCKET_NAME` = `(e.g., comfy)`
6. Click **Deploy**.
