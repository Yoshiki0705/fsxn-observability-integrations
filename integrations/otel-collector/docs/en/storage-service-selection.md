# Storage Service Selection Note

## Context

This project generates telemetry FROM FSx for ONTAP. It does not prescribe FSx for ONTAP as the storage layer for all logs or telemetry data.

## Use the Right Storage for the Job

| Storage Service | Best For | Not For |
|----------------|----------|---------|
| **FSx for ONTAP** | Enterprise file workloads, ONTAP data management, audit log source | General-purpose log archive |
| **Amazon S3** | Durable object storage, raw audit archive, data lake, long-term retention | Low-latency file access |
| **Amazon EFS** | Shared POSIX file storage for Linux workloads | Windows workloads, block storage |
| **Amazon EBS** | Block storage attached to EC2 instances | Shared file access, object storage |

## FSx for ONTAP S3 Access Points

S3 Access Points attached to FSx for ONTAP volumes allow S3 API access to file data without copying it to a separate S3 bucket. Key characteristics:

- Data remains on the FSx for ONTAP file system
- Accessible via NFS, SMB, and S3 API simultaneously
- S3 API latency: tens of milliseconds (not sub-millisecond like native S3)
- Throughput depends on the FSx file system's provisioned throughput capacity
- Not equivalent to standard S3 bucket scaling characteristics

> Source: [AWS FSx for ONTAP — Accessing data via S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
