#!/bin/bash
set -euo pipefail

# FPolicy Fargate Service Control
#
# Start/stop the FPolicy Fargate service for cost optimization.
# After starting, you must update the ONTAP External Engine IP
# (use fpolicy-update-engine-ip.sh --auto).
#
# Usage:
#   ./fpolicy-fargate-control.sh start    # Scale to 1 task
#   ./fpolicy-fargate-control.sh stop     # Scale to 0 tasks
#   ./fpolicy-fargate-control.sh status   # Show current state

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
ECS_CLUSTER="${ECS_CLUSTER:-fsxn-fpolicy-server-cluster}"
ECS_SERVICE="${ECS_SERVICE:-fsxn-fpolicy-server-service}"

case "${1:-status}" in
  start)
    echo "🚀 Starting FPolicy Fargate service..."
    aws ecs update-service \
      --cluster "${ECS_CLUSTER}" \
      --service "${ECS_SERVICE}" \
      --desired-count 1 \
      --region "${AWS_REGION}" \
      --query "service.{Status:status,Desired:desiredCount}" \
      --output table

    echo ""
    echo "⏳ Waiting for task to reach RUNNING state..."
    aws ecs wait services-stable \
      --cluster "${ECS_CLUSTER}" \
      --services "${ECS_SERVICE}" \
      --region "${AWS_REGION}" 2>/dev/null || true

    # Get task IP
    TASK_ARN=$(aws ecs list-tasks \
      --cluster "${ECS_CLUSTER}" \
      --service-name "${ECS_SERVICE}" \
      --desired-status RUNNING \
      --query "taskArns[0]" \
      --output text \
      --region "${AWS_REGION}")

    if [[ "${TASK_ARN}" != "None" && -n "${TASK_ARN}" ]]; then
      TASK_IP=$(aws ecs describe-tasks \
        --cluster "${ECS_CLUSTER}" \
        --tasks "${TASK_ARN}" \
        --query "tasks[0].containers[0].networkInterfaces[0].privateIpv4Address" \
        --output text \
        --region "${AWS_REGION}")
      echo ""
      echo "✅ Fargate task running at IP: ${TASK_IP}"
      echo ""
      echo "⚠️  Next step: Update ONTAP FPolicy External Engine:"
      echo "   ./shared/scripts/fpolicy-update-engine-ip.sh --auto"
    else
      echo ""
      echo "⏳ Task not yet running. Check with: $0 status"
    fi
    ;;

  stop)
    echo "🛑 Stopping FPolicy Fargate service (scale to 0)..."
    aws ecs update-service \
      --cluster "${ECS_CLUSTER}" \
      --service "${ECS_SERVICE}" \
      --desired-count 0 \
      --region "${AWS_REGION}" \
      --query "service.{Status:status,Desired:desiredCount}" \
      --output table

    echo ""
    echo "✅ Service scaled to 0. Fargate task will stop within ~30 seconds."
    echo "   Monthly cost: $0 (no running tasks)"
    ;;

  status)
    echo "=== FPolicy Fargate Service Status ==="
    aws ecs describe-services \
      --cluster "${ECS_CLUSTER}" \
      --services "${ECS_SERVICE}" \
      --region "${AWS_REGION}" \
      --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount,Pending:pendingCount}" \
      --output table

    TASK_ARN=$(aws ecs list-tasks \
      --cluster "${ECS_CLUSTER}" \
      --service-name "${ECS_SERVICE}" \
      --desired-status RUNNING \
      --query "taskArns[0]" \
      --output text \
      --region "${AWS_REGION}" 2>/dev/null || echo "None")

    if [[ "${TASK_ARN}" != "None" && -n "${TASK_ARN}" ]]; then
      echo ""
      echo "Running Task:"
      aws ecs describe-tasks \
        --cluster "${ECS_CLUSTER}" \
        --tasks "${TASK_ARN}" \
        --query "tasks[0].{IP:containers[0].networkInterfaces[0].privateIpv4Address,StartedAt:startedAt,Health:healthStatus}" \
        --output table \
        --region "${AWS_REGION}"
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
