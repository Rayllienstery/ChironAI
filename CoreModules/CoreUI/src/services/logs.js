import { getLogs } from './api';

let pollingInterval = null;
let lastLogId = 0;

export function startLogPolling(sessionId, callback, interval = 3000) {
  stopLogPolling();
  
  const poll = async () => {
    try {
      const data = await getLogs(sessionId, { 
        since_id: lastLogId,
        limit: 100 
      });
      
      if (data.logs && data.logs.length > 0) {
        lastLogId = Math.max(...data.logs.map(log => log.id));
        callback(data.logs);
      }
    } catch (error) {
      console.error('Log polling error:', error);
    }
  };
  
  // Initial poll
  poll();
  
  // Set up interval
  pollingInterval = setInterval(poll, interval);
}

export function stopLogPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
  lastLogId = 0;
}


