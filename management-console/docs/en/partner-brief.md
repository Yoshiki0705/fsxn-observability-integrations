# FSx for ONTAP Management Console — Partner Brief

## Customer Challenge

Storage administrators managing Amazon FSx for NetApp ONTAP need unified monitoring and management capabilities without relying on external SaaS platforms or ONTAP CLI expertise.

## Solution Pattern

Self-hosted management console deployed within the customer's VPC using AWS managed services:
- **Monitoring**: NetApp Harvest → Amazon Managed Prometheus → Amazon Managed Grafana (20+ dashboards)
- **Management**: Low-code UI (Appsmith/ToolJet) on ECS Fargate with ONTAP REST API integration
- **Authentication**: Amazon Cognito with MFA support

## Key Differentiators

| vs NetApp DII/BlueXP | vs Custom Development | vs CLI-only |
|----------------------|----------------------|-------------|
| No external SaaS dependency | No React/frontend development | GUI for all operations |
| VPC-internal data residency | Pre-built ONTAP dashboards | Reduced training time |
| AWS-native authentication | CloudFormation deployment | Audit trail built-in |
| Customer-owned infrastructure | Low-code UI customization | Error prevention (validation) |

## PoC Success Criteria

| Criteria | Measurement | Target |
|----------|-------------|--------|
| Deployment | All 5 stacks CREATE_COMPLETE | < 30 minutes |
| Metrics | Grafana dashboard shows ONTAP data | < 5 min after deploy |
| Operations | Volume create/resize/delete via UI | < 5 sec response |
| Authentication | Cognito login → access both layers | Single sign-on |

## Deployment Requirements

- Existing VPC with 2+ AZs (public + private subnets)
- FSx for ONTAP file system with management endpoint
- AWS CLI v2, no CDK/SAM required
- Estimated cost: ~$0.30/hour (NAT GW + ECS + RDS + VPC Endpoints)

## Workshop Flow (90 minutes)

1. **Architecture Review** (15 min) — 2-layer design, component roles
2. **Deploy Stack 1-2** (15 min) — Network + Auth (live demo)
3. **Deploy Stack 3-5** (30 min) — Observability + Console + Monitoring
4. **UI Walkthrough** (20 min) — Volume management, Grafana dashboards
5. **Q&A + Next Steps** (10 min) — Customization options, production hardening

## Next Steps After PoC

1. Custom domain + ACM certificate for ALB
2. Grafana dashboard customization for customer's specific volumes/SVMs
3. RBAC configuration (Cognito groups → Admin/Viewer roles)
4. Integration with existing observability pipeline (if applicable)

## Resources

- GitHub: `management-console/` directory
- Setup Guide: `docs/en/setup-guide.md`
- Local Dev: `docs/en/local-dev-guide.md`
