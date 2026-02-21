import { Navigate, Route, Routes } from 'react-router-dom';

import { ToastProvider } from '@/context/ToastContext';
import { ConfirmDialogProvider } from '@/context/ConfirmDialogContext';
import SummaryPage from '@/pages/SummaryPage';
import SourcesPage from '@/pages/SourcesPage';
import GroupsPage from '@/pages/GroupsPage';
import SettingsPage from '@/pages/SettingsPage';
import SettingsAdvancedPage from '@/pages/SettingsAdvancedPage';
import InstantLabPage from '@/pages/InstantLabPage';
import SchedulesPage from '@/pages/SchedulesPage';
import MemoryPage from '@/pages/MemoryPage';
import './styles/app.css';

const App = () => {
  return (
    <ToastProvider>
      <ConfirmDialogProvider>
        <Routes>
          <Route path="/" element={<SummaryPage />} />
          <Route path="/brief/:id" element={<SummaryPage />} />
          <Route path="/memory/:id" element={<MemoryPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/groups" element={<GroupsPage />} />
          <Route path="/instant" element={<InstantLabPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/advanced" element={<SettingsAdvancedPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ConfirmDialogProvider>
    </ToastProvider>
  );
};

export default App;
