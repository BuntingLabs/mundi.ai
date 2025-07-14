---
title: FedRAMP High Deployment
description: Deploying Mundi in a FedRAMP High environment (AWS GovCloud, Azure Government)
---

# FedRAMP High Deployment

:::note
Bunting Labs, Inc. is not FedRAMP Authorized.
:::

Mundi can be deployed to federal users, even though we are not FedRAMP authorized. Because Bunting Labs is not FedRAMP authorized, deploying Mundi requires an on-premises deployment in a FedRAMP authorized cloud. These are the docs for deploying Mundi to Amazon AWS GovCloud and Microsoft Azure Government.

:::note
Deployment configurations for Mundi can change over time. For the most up-to-date
information, [schedule a call](https://cal.com/buntinglabs/30min) with us.
:::

This deployment option is ideal for securely using Mundi when full network disconnection is not required. If you need to run Mundi completely offline in an air-gapped environment, see the [air gapped Mundi guide](./air-gapped.md).

For all deployment options, Bunting Labs does not need access to any servers or data, and can provide all support remotely. Your IT team can self-manage the Kubernetes environment, working closely with our engineering team to work through any issues in a privacy-preserving manner.

## Amazon AWS GovCloud

Mundi can run on AWS Elastic Kubernetes Service in GovCloud.

Amazon Bedrock provides access to LLMs within GovCloud, ensuring that traffic never leaves GovCloud.

## Microsoft Azure Government

Mundi can run on Azure Kubernetes Service in Azure Government.

Mundi can connect to Azure OpenAI, which is also FedRAMP High. 