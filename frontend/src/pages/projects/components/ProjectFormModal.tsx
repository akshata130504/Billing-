import React, { useState, useEffect } from 'react';
import { Project, ProjectStatus, BillingMethod } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';
import { validateSensibleName, validateNonNegativeMoney, validateDateNotBefore, parseStrictNumber } from '../../../utils/validation';
import { CustomerCombobox } from '../../../components/common/CustomerCombobox';

interface ProjectFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    name: string;
    /** Linked customer record: the project bills this customer. */
    customerId: string;
    customer: string;
    description: string;
    status: ProjectStatus;
    startDate: string;
    endDate: string;
    billingMethod: BillingMethod;
    budget: number;
    notes?: string;
  }) => void;
  initialProject?: Project | null;
  /** Deprecated: customers are now picked from the customer records. Kept for callers. */
  customerSuggestions?: string[];
}

export function ProjectFormModal({
  isOpen,
  onClose,
  onSubmit,
  initialProject,
}: ProjectFormModalProps) {
  const isEditing = Boolean(initialProject);

  const [name, setName] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [customer, setCustomer] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<ProjectStatus>('active');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [billingMethod, setBillingMethod] = useState<BillingMethod>('fixed_price');
  const [budget, setBudget] = useState('100000');
  const [notes, setNotes] = useState('');

  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (initialProject) {
      setName(initialProject.name);
      setCustomerId(initialProject.customerId || '');
      setCustomer(initialProject.customer);
      setDescription(initialProject.description || '');
      setStatus(initialProject.status);
      setStartDate(initialProject.startDate || '');
      setEndDate(initialProject.endDate || '');
      setBillingMethod(initialProject.billingMethod || 'fixed_price');
      setBudget(initialProject.budget ? String(initialProject.budget) : '0');
      setNotes(initialProject.notes || '');
    } else {
      setName('');
      setCustomerId('');
      setCustomer('');
      setDescription('');
      setStatus('active');
      const today = new Date().toISOString().split('T')[0];
      setStartDate(today);
      const threeMonthsLater = new Date();
      threeMonthsLater.setMonth(threeMonthsLater.getMonth() + 3);
      setEndDate(threeMonthsLater.toISOString().split('T')[0]);
      setBillingMethod('fixed_price');
      setBudget('100000');
      setNotes('');
    }
    setErrors({});
  }, [initialProject, isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    const nameError = validateSensibleName(name, 'Project name');
    if (nameError) {
      newErrors.name = nameError;
    }

    if (!customerId) {
      newErrors.customer = initialProject && !initialProject.customerId && customer
        ? `Link "${customer}" to a customer record so the project can be invoiced`
        : 'Customer is required';
    }

    const budgetError = validateNonNegativeMoney(budget, 'Budget');
    if (budgetError) {
      newErrors.budget = budgetError;
    }
    const numBudget = parseStrictNumber(budget) ?? 0;

    const dateError = validateDateNotBefore(endDate, startDate, 'End date', 'start date');
    if (dateError) {
      newErrors.endDate = dateError;
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    onSubmit({
      name: name.trim(),
      customerId,
      customer: customer.trim(),
      description: description.trim(),
      status,
      startDate,
      endDate,
      billingMethod,
      budget: numBudget,
      notes: notes.trim(),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Project' : 'Create New Project'}
      description={
        isEditing
          ? 'Update project scope, timelines, billing rates, and budget'
          : 'Define customer engagement terms, timelines, and financial limits'
      }
      size="lg"
      footer={
        <>
          <Button variant="outline" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            form="project-form"
          >
            {isEditing ? 'Save Changes' : 'Create Project'}
          </Button>
        </>
      }
    >
      <form id="project-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Project Name */}
          <div className="sm:col-span-2">
            <Input
              label="Project Name"
              required
              placeholder="e.g. Website Revamp, Cloud Infrastructure Migration"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={errors.name}
            />
          </div>

          {/* Customer */}
          <div>
            <CustomerCombobox
              label="Customer"
              required
              value={customerId}
              error={errors.customer}
              onChange={(id, cust) => {
                setCustomerId(id);
                setCustomer(cust?.display_name || '');
              }}
            />
          </div>

          {/* Billing Method */}
          <div>
            <Select
              label="Billing Method"
              required
              value={billingMethod}
              onChange={(e) => setBillingMethod(e.target.value as BillingMethod)}
              options={[
                { value: 'fixed_price', label: 'Fixed Price' },
                { value: 'time_and_material', label: 'Time & Material' },
                { value: 'non_billable', label: 'Non-Billable (Internal/R&D)' },
              ]}
            />
          </div>

          {/* Project Status */}
          <div>
            <Select
              label="Project Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              options={[
                { value: 'draft', label: 'Draft' },
                { value: 'active', label: 'Active' },
                { value: 'on_hold', label: 'On Hold' },
                { value: 'completed', label: 'Completed' },
                { value: 'cancelled', label: 'Cancelled' },
              ]}
            />
          </div>

          {/* Project Budget */}
          <div>
            <Input
              label="Project Budget (₹)"
              type="number"
              min="0"
              step="1000"
              placeholder="e.g. 150000"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              error={errors.budget}
            />
          </div>

          {/* Start Date */}
          <div>
            <Input
              label="Start Date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          {/* End Date */}
          <div>
            <Input
              label="End Date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              error={errors.endDate}
            />
          </div>

          {/* Description */}
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Description
            </label>
            <textarea
              rows={2}
              placeholder="Describe deliverables, key milestones, and business goals..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            />
          </div>

          {/* Notes */}
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Internal Notes (Optional)
            </label>
            <textarea
              rows={2}
              placeholder="Any billing constraints, SLA terms, or team instructions..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
