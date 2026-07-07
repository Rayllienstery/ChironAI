import React, { useMemo, useRef, useState } from "react";
import {
  CreateCollectionModal,
  CreatePipelineModal,
  DeletePipelineConfirmModal,
  SourceModal,
} from "./CrawlerModals";
import ActionableError from "./ActionableError";
import "../styles/components/CoreUIButtons.css";
import "../styles/components/CrawlerTab.css";
import { useOptionalNotificationCenter } from "./NotificationCenterContext";
import CrawlerResultModal from "./crawlerTab/CrawlerResultModal";
import CrawlerSourcesPanel from "./crawlerTab/CrawlerSourcesPanel";
import CrawlerTabHeader from "./crawlerTab/CrawlerTabHeader";
import MdPipelinePreviewModal from "./crawlerTab/MdPipelinePreviewModal";
import MdPipelineSection from "./crawlerTab/MdPipelineSection";
import { useCreateCollectionFlow } from "./crawlerTab/useCreateCollectionFlow";
import { useCrawlerSection } from "./crawlerTab/useCrawlerSection";
import { useMdPipelineSection } from "./crawlerTab/useMdPipelineSection";
import { createCrawlerTourSteps } from "./onboarding/contextualTours.js";
import { useContextualTour } from "./onboarding/useContextualTour.js";

function CrawlerTab() {
  const nc = useOptionalNotificationCenter();
  const [activeSection, setActiveSection] = useState("crawler");

  const crawler = useCrawlerSection({ nc, activeSection });
  const createCollection = useCreateCollectionFlow({
    nc,
    activeSection,
    sources: crawler.sources,
    setError: crawler.setError,
    loadCollections: crawler.loadCollections,
  });
  const mdPipeline = useMdPipelineSection({ activeSection });

  const tourActionsRef = useRef({});
  tourActionsRef.current = {
    setActiveSection,
    openCreateCollectionModal: () => createCollection.setShowCreateModal(true),
    closeModals: () => {
      crawler.setShowAddSourceModal(false);
      createCollection.setShowCreateModal(false);
    },
    selectFirstSource: () => {
      const first = crawler.sources[0];
      if (first && crawler.selectedSource !== first.id) {
        crawler.handleSourceClick(first.id);
      }
    },
    expandFirstMdStep: () => {
      const steps = mdPipeline.pipelineData?.steps || [];
      if (steps.length === 0) return;
      const stepKey = steps[0].id || "idx-0";
      if (!mdPipeline.expandedMdSteps.has(stepKey)) {
        mdPipeline.toggleMdStepExpanded(stepKey);
      }
    },
  };

  const crawlerTourSteps = useMemo(
    () =>
      createCrawlerTourSteps({
        setActiveSection: (...args) => tourActionsRef.current.setActiveSection?.(...args),
        openCreateCollectionModal: () =>
          tourActionsRef.current.openCreateCollectionModal?.(),
        closeModals: () => tourActionsRef.current.closeModals?.(),
        selectFirstSource: () => tourActionsRef.current.selectFirstSource?.(),
        expandFirstMdStep: () => tourActionsRef.current.expandFirstMdStep?.(),
      }),
    [],
  );
  useContextualTour("crawler", crawlerTourSteps, !crawler.loading);

  return (
    <div className="crawler-tab tab-view">
      <CrawlerTabHeader
        activeSection={activeSection}
        onSectionChange={setActiveSection}
        selectedSource={crawler.selectedSource}
        sources={crawler.sources}
        selectedSourceIds={crawler.selectedSourceIds}
        crawlingSources={crawler.crawlingSources}
        busy={crawler.busy}
        onCrawlSource={crawler.handleCrawlSource}
        onCrawlAll={crawler.handleCrawlAll}
        onCrawlSelected={crawler.handleCrawlSelected}
        onAddSource={() => crawler.setShowAddSourceModal(true)}
        onCreateCollection={() => createCollection.setShowCreateModal(true)}
        onRefresh={crawler.handleRefresh}
      />

      {activeSection === "crawler" &&
        crawler.crawlAllResults.length > 0 &&
        crawler.crawlingSources.size === 0 && (
          <CrawlerResultModal
            results={crawler.crawlAllResults}
            onClose={() => crawler.setCrawlAllResults([])}
          />
        )}

      {activeSection === "crawler" && crawler.error && (
        <ActionableError error={crawler.error} onRetry={crawler.handleRefresh} />
      )}

      {activeSection === "crawler" && (
        <CrawlerSourcesPanel
          loading={crawler.loading}
          sources={crawler.sources}
          selectedSource={crawler.selectedSource}
          sourcePages={crawler.sourcePages}
          selectedSourceIds={crawler.selectedSourceIds}
          crawlingSources={crawler.crawlingSources}
          onToggleSelectAll={crawler.handleToggleSelectAll}
          onToggleSourceSelected={crawler.toggleSourceSelected}
          onSourceClick={crawler.handleSourceClick}
          onEditSource={crawler.handleEditSource}
          onCrawlSource={crawler.handleCrawlSource}
        />
      )}

      {activeSection === "md-pipeline" && (
        <MdPipelineSection
          pipelineError={mdPipeline.pipelineError}
          selectedPipelineName={mdPipeline.selectedPipelineName}
          setSelectedPipelineName={mdPipeline.setSelectedPipelineName}
          pipelineList={mdPipeline.pipelineList}
          pipelineLoading={mdPipeline.pipelineLoading}
          pipelineSaving={mdPipeline.pipelineSaving}
          pipelineSaveToast={mdPipeline.pipelineSaveToast}
          pipelinePreviewSourceId={mdPipeline.pipelinePreviewSourceId}
          setPipelinePreviewSourceId={mdPipeline.setPipelinePreviewSourceId}
          pipelinePreviewSources={mdPipeline.pipelinePreviewSources}
          pipelinePreviewSourcesLoading={mdPipeline.pipelinePreviewSourcesLoading}
          pipelinePreviewFilename={mdPipeline.pipelinePreviewFilename}
          setPipelinePreviewFilename={mdPipeline.setPipelinePreviewFilename}
          pipelinePreviewFiles={mdPipeline.pipelinePreviewFiles}
          pipelinePreviewFilesLoading={mdPipeline.pipelinePreviewFilesLoading}
          previewLoading={mdPipeline.previewLoading}
          pipelineData={mdPipeline.pipelineData}
          expandedMdSteps={mdPipeline.expandedMdSteps}
          showAddStepMenu={mdPipeline.showAddStepMenu}
          setShowAddStepMenu={mdPipeline.setShowAddStepMenu}
          onCreatePipeline={mdPipeline.handleCreatePipeline}
          onSavePipeline={mdPipeline.handleSaveMdPipeline}
          onPreviewPipeline={mdPipeline.handlePreviewMdPipeline}
          onDeletePipeline={mdPipeline.handleDeletePipelineClick}
          onToggleStepExpanded={mdPipeline.toggleMdStepExpanded}
          onChangeStepType={mdPipeline.handleChangeMdStepType}
          onMoveStep={mdPipeline.handleMoveMdStep}
          onRemoveStep={mdPipeline.handleRemoveMdStep}
          onUpdateStep={mdPipeline.handleUpdateMdStep}
          onUpdateLine={mdPipeline.updateMdStepLine}
          onAddLine={mdPipeline.addMdStepLine}
          onRemoveLine={mdPipeline.removeMdStepLine}
          onAddStep={mdPipeline.handleAddMdStep}
          onRetryPipeline={mdPipeline.retryPipelineLoad}
        />
      )}

      <MdPipelinePreviewModal
        previewResult={mdPipeline.previewResult}
        pipelinePreviewFilename={mdPipeline.pipelinePreviewFilename}
        onClose={() => mdPipeline.setPreviewResult(null)}
      />

      <CreatePipelineModal
        open={mdPipeline.showCreatePipelineModal}
        newPipelineName={mdPipeline.newPipelineName}
        onChangeName={mdPipeline.setNewPipelineName}
        onConfirm={mdPipeline.handleConfirmCreatePipeline}
        onClose={() => mdPipeline.setShowCreatePipelineModal(false)}
      />
      <DeletePipelineConfirmModal
        open={mdPipeline.showDeletePipelineConfirm}
        pipelineName={mdPipeline.selectedPipelineName}
        onConfirm={mdPipeline.handleConfirmDeletePipeline}
        onClose={() => mdPipeline.setShowDeletePipelineConfirm(false)}
      />
      <CreateCollectionModal
        open={createCollection.showCreateModal}
        createProgress={createCollection.createProgress}
        createForm={createCollection.createForm}
        onFormChange={createCollection.setCreateForm}
        createEmbedCatalog={createCollection.createEmbedCatalog}
        createEmbedDefaults={createCollection.createEmbedDefaults}
        sources={crawler.sources}
        toggleSourceInForm={createCollection.toggleSourceInForm}
        creating={createCollection.creating}
        createCanceling={createCollection.createCanceling}
        onCreate={createCollection.handleCreateCollection}
        onCancelCreate={createCollection.handleCancelCreateCollection}
        onClose={() => createCollection.setShowCreateModal(false)}
      />
      <SourceModal
        open={crawler.showAddSourceModal}
        mode="add"
        sourceId={null}
        form={crawler.addSourceForm}
        onFormChange={crawler.setAddSourceForm}
        loading={crawler.addingSource}
        onSubmit={crawler.handleAddSource}
        onClose={() => crawler.setShowAddSourceModal(false)}
      />
      <SourceModal
        open={crawler.showEditSourceModal}
        mode="edit"
        sourceId={crawler.editingSourceId}
        form={crawler.editSourceForm}
        onFormChange={crawler.setEditSourceForm}
        loading={crawler.updatingSource}
        onSubmit={crawler.handleUpdateSource}
        onClose={() => crawler.setShowEditSourceModal(false)}
      />
    </div>
  );
}

export default CrawlerTab;
