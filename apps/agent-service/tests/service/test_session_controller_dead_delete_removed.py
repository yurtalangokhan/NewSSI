"""Spec: SessionService.delete_chat_session must not exist.

It deleted the thread row via delete_thread_from_store but never called
saver.adelete_thread -- reproducing the exact bug (B13) that
ThreadController.delete_thread was already fixed to avoid: leaving the
checkpoint behind resurrects the old conversation if the same
chat_session_id is ever reused. This method had zero callers (confirmed:
grep of the whole src/ tree finds SessionService only used, via
UserController, for get_llm_providers/get_llm_built_in_options/
get_ollama_models) and zero test coverage -- a landmine, not a feature, so
it's removed rather than fixed in place. The real, correct delete path is
ChatManagementService.delete_chat_session -> ThreadController.delete_thread, which
already purges both the row and the checkpoint.
"""

from service.threads.session_service import SessionService


def test_session_controller_no_longer_exposes_a_duplicate_delete_path():
    assert not hasattr(SessionService, "delete_chat_session")
