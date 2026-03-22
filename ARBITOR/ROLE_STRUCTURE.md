# Arbitor Role-Based File Structure

## Role 1: Frontend + Enforcement UI Engineer
- `arbitor_app/roles/role_1_ui/login_window.py`
- `arbitor_app/roles/role_1_ui/admin_panel.py`
- `arbitor_app/roles/role_1_ui/widgets.py`
- `arbitor_app/roles/role_1_ui/enforcement_worker.py`
- `arbitor_app/roles/role_1_ui/ui_utils.py`

## Role 2: Database Engineer
- `arbitor_app/roles/role_2_database/database_manager.py`

## Role 3: Session & Authentication Engine
- `arbitor_app/roles/role_3_session_auth/session_auth_engine.py`

## Role 4: Policy Engine
- `arbitor_app/roles/role_4_policy_engine/policy_engine.py`

## Role 5: Download & File Control Engine
- `arbitor_app/roles/role_5_download_control/download_control_engine.py`

## Role 6: Sync Engine + Reliability
- `arbitor_app/roles/role_6_sync_engine/sync_worker.py`

## Entrypoint
- `ARBITOR.py`
- `arbitor_app/main.py`
