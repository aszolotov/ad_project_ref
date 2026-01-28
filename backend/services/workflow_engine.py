import json
import threading
import logging
from backend.core.config import settings
from backend.services.ldap_service import ldap_service, ldap_pool
from ldap3 import MODIFY_ADD

logger = logging.getLogger(__name__)


class WorkflowEngine:
    def trigger(self, event_type: str, context: dict):
        """Запуск workflow для события в фоновом потоке"""
        threading.Thread(target=self._process, args=(event_type, context), daemon=True).start()

    def _process(self, event, context):
        """Обработка события и запуск соответствующих workflow"""
        if not settings.WORKFLOWS_DIR.exists():
            return
        
        for workflow_file in settings.WORKFLOWS_DIR.glob("*.json"):
            try:
                with open(workflow_file, 'r', encoding='utf-8') as fp:
                    workflow = json.load(fp)
                
                # Проверяем, что workflow включен и триггер совпадает
                if workflow.get('enabled', True) and workflow.get('trigger') == event:
                    logger.info(f"Executing workflow {workflow_file.name} for event {event}")
                    self._execute_steps(workflow.get('steps', []), context)
            except Exception as e:
                logger.error(f"Workflow Error in {workflow_file}: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Step failed: {step.get('type', 'unknown')} - {e}", exc_info=True)

    def _handle_approval(self, step, ctx):
        """Создание запроса на согласование"""
        from backend.db.database import SessionLocal
        from backend.services.approval_service import approval_service
        
        approver = step.get('approver', 'admin')
        payload = {
            "workflow_step": step,
            "context": ctx
        }
        
        db = SessionLocal()
        try:
            # TODO: В реальной системе нужно приостановить workflow
            # Сейчас мы просто создаем заявку, но workflow продолжится (или завершится)
            # Если мы хотим блокировать, то нужно менять архитектуру engine на state machine
            # Для MVP: создаем заявку, и если это последний шаг - ок.
            # Если не последний - то следующие шаги выполнятся сразу (что плохо).
            # Поэтому пока считаем, что wait_for_approval - это терминальный шаг в этой цепочке,
            # а продолжение должно быть инициировано вручную или через другой триггер.
            
            approval_service.create_request(
                db=db,
                requester=ctx.get('username', 'system'),
                action_type="workflow_step",
                payload=payload,
                approver=approver
            )
            logger.info(f"Approval request created for {approver}")
        finally:
            db.close()

    def _execute_steps(self, steps, ctx):
        """Выполнение шагов workflow"""
        for step in steps:
            try:
                step_type = step.get('type')
                
                if step_type == 'wait_for_approval':
                    self._handle_approval(step, ctx)
                    # Прерываем выполнение, так как ждем подтверждения
                    # В будущем: сохранить состояние и возобновить
                    break 
                
                if step_type == 'email':
                    # ... (existing email logic)
                    to_email = step.get('to', '').format(**ctx) if 'to' in step else ''
                    subject = step.get('subject', '').format(**ctx) if 'subject' in step else ''
                    body = step.get('body', '').format(**ctx) if 'body' in step else ''
                    
                    # Реализация отправки email
                    import smtplib
                    from email.mime.text import MIMEText
                    from email.mime.multipart import MIMEMultipart

                    smtp_server = getattr(settings, 'SMTP_SERVER', 'localhost')
                    smtp_port = getattr(settings, 'SMTP_PORT', 25)
                    smtp_user = getattr(settings, 'SMTP_USER', None)
                    smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
                    from_email = getattr(settings, 'SMTP_FROM', 'noreply@example.com')

                    try:
                        msg = MIMEMultipart()
                        msg['From'] = from_email
                        msg['To'] = to_email
                        msg['Subject'] = subject
                        msg.attach(MIMEText(body, 'plain'))

                        if smtp_server == 'localhost':
                             logger.info(f"STUB: Sending email to {to_email} with subject {subject}")
                        else:
                            with smtplib.SMTP(smtp_server, smtp_port) as server:
                                if smtp_user and smtp_password:
                                    server.starttls()
                                    server.login(smtp_user, smtp_password)
                                server.send_message(msg)
                            logger.info(f"Email sent to {to_email}")
                    except Exception as email_err:
                        logger.error(f"Failed to send email: {email_err}")
                    
                elif step_type == 'webhook':
                    # ... (existing webhook logic)
                    url = step.get('url', '').format(**ctx) if isinstance(step.get('url'), str) else step.get('url')
                    method = step.get('method', 'POST').upper()
                    data = step.get('data', {})
                    
                    # Подстановка переменных в data
                    formatted_data = {}
                    for k, v in data.items():
                        if isinstance(v, str):
                            formatted_data[k] = v.format(**ctx)
                        else:
                            formatted_data[k] = v
                    
                    import requests
                    try:
                        response = requests.request(
                            method=method,
                            url=url,
                            json=formatted_data,
                            timeout=10
                        )
                        response.raise_for_status()
                        logger.info(f"Webhook sent to {url}: {response.status_code}")
                    except Exception as webhook_error:
                        logger.error(f"Webhook error for {url}: {webhook_error}")
                        
                elif step_type == 'add_to_group':
                    # ... (existing add_to_group logic)
                    user_dn = ctx.get('dn')
                    group_dn = step.get('group_dn')
                    
                    if not user_dn or not group_dn:
                        logger.warning(f"add_to_group: missing user_dn or group_dn. user_dn={user_dn}, group_dn={group_dn}")
                        continue
                    
                    try:
                        conn = ldap_pool.get_connection()
                        try:
                            conn.modify(group_dn, {'member': [(MODIFY_ADD, [user_dn])]})
                            logger.info(f"User {user_dn} added to group {group_dn}")
                        finally:
                            ldap_pool.release(conn)
                    except Exception as group_error:
                        logger.error(f"Failed to add {user_dn} to group {group_dn}: {group_error}")
                
                elif step_type == 'condition':
                    # ... (existing condition logic)
                    # Обработка условий (if/else)
                    field = step.get('field')
                    operator = step.get('operator', 'eq')
                    value = step.get('value')
                    
                    # Получаем значение из контекста
                    ctx_value = ctx.get(field, '')
                    
                    # Проверка условия
                    condition_met = False
                    if operator == 'eq':
                        condition_met = str(ctx_value) == str(value)
                    elif operator == 'neq':
                        condition_met = str(ctx_value) != str(value)
                    elif operator == 'contains':
                        condition_met = str(value) in str(ctx_value)
                    
                    # Выполняем соответствующие шаги
                    steps_to_execute = step.get('then', []) if condition_met else step.get('else', [])
                    if steps_to_execute:
                        self._execute_steps(steps_to_execute, ctx)
                        
            except Exception as e:
                logger.error(f"Step failed: {step.get('type', 'unknown')} - {e}", exc_info=True)

workflow_engine = WorkflowEngine()
