---
title: Air Gapped Mundi
description: Deploying Mundi in a completely disconnected environment for maximum security
---

# Air Gapped Deployment

For government and commercial users who require maximum security, Mundi's enterprise features are available to be run completely disconnected from the internet.

:::note
Deploying air gapped Mundi can be done to accomodate your exact needs. For the most up-to-date
information, [schedule a call](https://cal.com/buntinglabs/30min) with us.
:::

## Deploying on Kubernetes

We use a Kubernetes environment provisioned by [Helm charts](https://helm.sh/). Any CNCF‑certified Kubernetes distribution works—whether a managed cloud service, a bare‑metal cluster, or an edge‑scale micro‑k3s node.

Images are kept in your private registry, so the cluster can function with zero outbound traffic.

## Disconnected LLM and GPU requirements

Air gapped Mundi is designed to be used with a variety of GPUs and models. For some users, this may mean using small models on a small GPU, trading degraded LLM performance for lower infrastructure costs. Or, if you have access to high-end data center GPUs, we can help you use frontier models.

If your organization has an air-gapped LLM already, Mundi can likely make use of that.

Reach out to us and we can help guide you to the best solution for your needs.

## Air gapped vs. hosted features

Air gapped Mundi has access to all core features available in enterprise Mundi—SSO, collaboration, and our latest LLM prompting research. Some features, such as the basemap we rely on, are changed to remove the need for a network connection, but all core functionality is maintained. 