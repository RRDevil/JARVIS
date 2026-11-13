import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApplicationManagerModal } from '../components/ApplicationManagerModal';
import * as integrationApi from '../services/integrationApi';
import { ApplicationManifest } from '../types/integrations';

describe('ApplicationManagerModal Component (Phase 5.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockApps: ApplicationManifest[] = [
    {
      app_id: 'browser.opera_gx',
      display_name: 'Opera GX',
      vendor: 'Opera Software',
      category: 'browser',
      description: 'Gaming browser with tab management and URL navigation.',
      process_rule: {
        executable_names: ['opera.exe'],
        window_title_patterns: ['Opera'],
        registry_app_paths_keys: ['opera.exe'],
        common_install_paths: [],
      },
      supported_providers: ['browser_automation', 'desktop_ui'],
      capabilities: [
        {
          id: 'browser.navigate',
          name: 'Navigate to URL',
          description: 'Navigate active or new tab to web address.',
          permission_level: 'controlled',
          risk_tier: 'LOW_RISK',
          supported_providers: ['browser_automation'],
        },
        {
          id: 'browser.read_page',
          name: 'Read Web Page Content',
          description: 'Extract visible text and accessibility tree from active page.',
          permission_level: 'read_only',
          risk_tier: 'READ_ONLY',
          supported_providers: ['browser_automation', 'desktop_ui'],
        },
      ],
      is_enabled: true,
      is_installed: true,
      installed_path: 'C:\\Users\\Asus\\AppData\\Local\\Programs\\Opera GX\\opera.exe',
      is_running: true,
      running_pids: [13032],
      running_window_handles: [66590],
      health_status: 'healthy',
    },
    {
      app_id: 'office.word',
      display_name: 'Microsoft Word',
      vendor: 'Microsoft Corporation',
      category: 'office',
      description: 'Document processing and native COM automation.',
      process_rule: {
        executable_names: ['winword.exe'],
        window_title_patterns: ['Word'],
        registry_app_paths_keys: ['winword.exe'],
        common_install_paths: [],
      },
      supported_providers: ['office_com', 'desktop_ui'],
      capabilities: [
        {
          id: 'word.read_document',
          name: 'Read Active Document',
          description: 'Read body text, paragraphs, and tables via COM automation.',
          permission_level: 'read_only',
          risk_tier: 'READ_ONLY',
          supported_providers: ['office_com'],
        },
      ],
      is_enabled: true,
      is_installed: true,
      installed_path: 'C:\\Program Files\\Microsoft Office\\Office16\\WINWORD.EXE',
      is_running: false,
      running_pids: [],
      running_window_handles: [],
      health_status: 'healthy',
    },
  ];

  it('renders application modal header, tabs, and application cards', async () => {
    vi.spyOn(integrationApi, 'fetchApplications').mockResolvedValue(mockApps);
    vi.spyOn(integrationApi, 'fetchIntegrationActivity').mockResolvedValue([]);

    render(<ApplicationManagerModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText(/INTEGRATED APPLICATIONS/i)).not.toBeNull();
    expect(screen.getByText(/PHASE 5.2 FRAMEWORK/i)).not.toBeNull();

    await waitFor(() => {
      expect(screen.getByText('Opera GX')).not.toBeNull();
      expect(screen.getByText('Microsoft Word')).not.toBeNull();
      expect(screen.getAllByText('INSTALLED').length).toBeGreaterThan(0);
      expect(screen.getByText('RUNNING')).not.toBeNull();
    });
  });

  it('filters applications by category', async () => {
    vi.spyOn(integrationApi, 'fetchApplications').mockResolvedValue(mockApps);
    vi.spyOn(integrationApi, 'fetchIntegrationActivity').mockResolvedValue([]);

    render(<ApplicationManagerModal isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Opera GX')).not.toBeNull();
    });

    // Click Office category filter
    const officeFilterBtn = screen.getByText(/MICROSOFT OFFICE/i);
    fireEvent.click(officeFilterBtn);

    await waitFor(() => {
      expect(screen.queryByText('Opera GX')).toBeNull();
      expect(screen.getByText('Microsoft Word')).not.toBeNull();
    });
  });

  it('allows expanding application details to view capabilities and providers', async () => {
    vi.spyOn(integrationApi, 'fetchApplications').mockResolvedValue(mockApps);
    vi.spyOn(integrationApi, 'fetchIntegrationActivity').mockResolvedValue([]);

    render(<ApplicationManagerModal isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Opera GX')).not.toBeNull();
    });

    // Click to expand Opera GX
    fireEvent.click(screen.getByText('Opera GX'));

    await waitFor(() => {
      expect(screen.getByText(/INTEGRATION PROVIDERS:/i)).not.toBeNull();
      expect(screen.getByText('browser_automation')).not.toBeNull();
      expect(screen.getByText('Navigate to URL')).not.toBeNull();
      expect(screen.getByText('Read Web Page Content')).not.toBeNull();
    });
  });

  it('toggles application enablement and updates backend policy', async () => {
    vi.spyOn(integrationApi, 'fetchApplications').mockResolvedValue(mockApps);
    vi.spyOn(integrationApi, 'fetchIntegrationActivity').mockResolvedValue([]);
    const updateSpy = vi.spyOn(integrationApi, 'updateAppPermissions').mockResolvedValue({
      app_id: 'browser.opera_gx',
      is_enabled: false,
      disabled_providers: [],
      disabled_capabilities: [],
      require_approval_overrides: {},
    });

    render(<ApplicationManagerModal isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getAllByText('ENABLED')[0]).not.toBeNull();
    });

    // Toggle first app
    fireEvent.click(screen.getAllByText('ENABLED')[0]);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({
        app_id: 'browser.opera_gx',
        is_enabled: false,
      });
    });
  });

  it('triggers on-demand discovery scan', async () => {
    vi.spyOn(integrationApi, 'fetchApplications').mockResolvedValue(mockApps);
    vi.spyOn(integrationApi, 'fetchIntegrationActivity').mockResolvedValue([]);
    const scanSpy = vi.spyOn(integrationApi, 'triggerAppDiscovery').mockResolvedValue(mockApps);

    render(<ApplicationManagerModal isOpen={true} onClose={vi.fn()} />);

    const refreshBtn = screen.getByText(/REFRESH DISCOVERY/i);
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(scanSpy).toHaveBeenCalledWith(true);
    });
  });
});
