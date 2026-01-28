$(document).ready(() => {
    // Init
    if (localStorage.getItem('ad_token')) {
        loadDashboard();
    }

    // Event Listeners
    $('#btn-create-user').click(() => ui.openModal('user-modal'));
});

function loadUsers() {
    ui.showLoader(true);
    api.getUsers(currentPage, currentOu)
       .then(data => {
           ui.renderTable('users-table', data.users);
           ui.renderPagination(data.total_pages);
       })
       .finally(() => ui.showLoader(false));
}
