class ApiClient {
    constructor() {
        this.baseUrl = '/api/v6';
        this.token = localStorage.getItem('ad_token');
    }

    async request(endpoint, method = 'GET', data = null) {
        const headers = { 
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json'
        };
        
        const config = { method, headers };
        if (data) config.body = JSON.stringify(data);

        const res = await fetch(`${this.baseUrl}${endpoint}`, config);
        if (res.status === 401) window.location.reload(); // Handle logout
        return res.json();
    }

    async getUsers(page, ou) {
        return this.request(`/users?page=${page}&ou=${ou}`);
    }
    
    async createUser(data) {
        return this.request('/users/create', 'POST', data);
    }
}

const api = new ApiClient();
